from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / "ck.txt"

JS_SCAN = r'''() => {
  const keys = /插入|导入文档|导入|文档|word|doc|edui42|drawer|dropdown|popover|portal/i;
  return {
    url: location.href,
    bodyHasInsert: document.body.innerText.includes('插入'),
    bodyHasImportDoc: document.body.innerText.includes('导入文档'),
    fileInputs: Array.from(document.querySelectorAll('input[type=file]')).map((el, i) => ({
      i, accept: el.getAttribute('accept'), id: el.id || '', cls: String(el.className || ''),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      html: el.outerHTML.slice(0, 300),
    })),
    edui42: (() => {
      const el = document.querySelector('#edui42');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {style: el.getAttribute('style'), cls: el.className, display: el.style.display,
        rect: {x:r.x,y:r.y,w:r.width,h:r.height},
        html: el.outerHTML.slice(0, 800)};
    })(),
    edui42_content: (() => {
      const el = document.querySelector('#edui42_content');
      if (!el) return null;
      return {html: el.innerHTML.slice(0, 1000), text: el.innerText.slice(0, 300),
        childCount: el.children.length, childHtml: Array.from(el.children).slice(0,20).map(c=>c.outerHTML.slice(0,200))};
    })(),
    newBjhInsertionDrawer: (() => {
      const els = Array.from(document.querySelectorAll('*')).filter(el => /bjhInsertionDrawer|BjhInsertion/i.test(el.id) && el.offsetParent !== null);
      return els.map(el => {
        const r = el.getBoundingClientRect();
        return {id: el.id, cls: String(el.className||''), txt: (el.innerText||'').slice(0,200), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0,400)};
      });
    })(),
    matches: Array.from(document.querySelectorAll('*')).map((el, i) => {
      const txt = (el.innerText||el.textContent||'').trim().replace(/\s+/g,' ');
      const r = el.getBoundingClientRect();
      return {i, tag:el.tagName, id:el.id||'', cls:String(el.className||''), txt:txt.slice(0,120), visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:el.outerHTML.slice(0,400)};
    }).filter(x => x.visible && keys.test([x.id,x.cls,x.txt,x.html].join(' '))).slice(0, 400),
    bodyVisiblePopovers: Array.from(document.querySelectorAll('[class*="popover"], [class*="drawer"], [class*="dropdown"], [class*="portal"], [role="dialog"], [role="tooltip"]')).map(el => {
      const r = el.getBoundingClientRect();
      const visible = !!(el.offsetWidth||el.offsetHeight||el.getClientRects().length);
      return {tag:el.tagName, id:el.id||'', cls:String(el.className||'').slice(0,200), txt:(el.innerText||'').slice(0,100), visible, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:el.outerHTML.slice(0,300)};
    }).filter(x => x.visible && (x.rect.w > 10 && x.rect.h > 10)).slice(0, 100),
  };
}'''

async def dump(page, outdir: Path, name: str):
    data = await page.evaluate(JS_SCAN)
    await page.screenshot(path=str(outdir / f'{name}.png'), full_page=True)
    (outdir / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data

async def try_click_text(page, text: str):
    loc = page.get_by_text(text, exact=True)
    cnt = await loc.count()
    for i in range(min(cnt, 10)):
        el = loc.nth(i)
        try:
            if await el.is_visible(timeout=1000):
                try:
                    await el.click(timeout=2000)
                    return f'click:{text}:{i}'
                except Exception:
                    try:
                        await el.click(timeout=2000, force=True)
                        return f'force:{text}:{i}'
                    except Exception:
                        pass
        except Exception:
            pass
    return None

async def try_dom_click(page, selector: str):
    try:
        await page.evaluate(f"document.querySelector('{selector}')?.click()")
        return f'dom:{selector}'
    except Exception:
        return None

async def main():
    outdir = base / 'debug' / 'insert_flow_final'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_insert_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: 首页
        await page.goto("https://baijiahao.baidu.com/", wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(6000)

        result = {'steps': []}
        result['steps'].append({'stage': 'home', **(await dump(page, outdir, '01_home'))})

        # Step 2: 发布作品
        await page.locator('#home-publish-btn').evaluate("el => el.click()")
        await page.wait_for_timeout(5000)
        result['steps'].append({'stage': 'after_publish', **(await dump(page, outdir, '02_after_publish'))})

        # Step 3: 点击"图文"
        await try_click_text(page, '图文')
        await page.wait_for_timeout(6000)
        result['steps'].append({'stage': 'after_tuwen', **(await dump(page, outdir, '03_after_tuwen'))})

        # Step 4: 关闭"我知道了"弹窗
        await try_click_text(page, '我知道了')
        await page.wait_for_timeout(1500)

        # Step 5: 聚焦 iframe 编辑器（关键步骤）
        try:
            frame = page.frame_locator('#ueditor_0')
            await frame.locator('body').click(timeout=3000)
            result['steps'].append({'action': 'focus_editor_frame', 'ok': True})
        except Exception as e:
            result['steps'].append({'action': 'focus_editor_frame', 'ok': False, 'err': str(e)})
        await page.wait_for_timeout(1000)

        result['steps'].append({'stage': 'before_insert_click', **(await dump(page, outdir, '04_before_insert'))})

        # Step 6: 点击"插入"
        insert_how = await try_click_text(page, '插入')
        if not insert_how:
            insert_how = await try_dom_click(page, '.FeEditorApp-_4ecaee52b311664f-entry')
        if not insert_how:
            insert_how = await try_dom_click(page, '#edui41_state')
        result['steps'].append({'action': 'click_insert', 'how': insert_how, 'url_after': page.url})

        # 立即连续扫描（抓住窗口期）
        for round_num in range(1, 5):
            await page.wait_for_timeout(800)  # 每个 800ms 扫一次
            snap = await dump(page, outdir, f'05_insert_{round_num}')
            snap_name = f'round_{round_num}'
            result['steps'].append({'stage': f'after_insert_round_{round_num}', **snap})

            # 如果发现 import doc 或 edui42 展开，说明命中了
            if snap.get('bodyHasImportDoc') or (snap.get('edui42') and snap['edui42'].get('style','').replace(' ','').find('display:none')<0):
                result['steps'].append({'note': 'IMPORT_DOC_OR_EDUI42_VISIBLE', 'round': round_num})
                break

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
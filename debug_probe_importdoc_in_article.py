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
URL = "https://baijiahao.baidu.com/"

JS_SCAN = r'''() => {
  const keys = /插入|导入文档|导入|文档|word|doc|upload|file|edui41|edui42|popover|dropdown|drawer|dialog/i;
  return {
    url: location.href,
    bodyHasImportDoc: document.body.innerText.includes('导入文档'),
    bodyHasInsert: document.body.innerText.includes('插入'),
    fileInputs: Array.from(document.querySelectorAll('input[type=file]')).map((el, i) => ({
      i,
      accept: el.getAttribute('accept'),
      id: el.id || '',
      cls: String(el.className || ''),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      html: el.outerHTML.slice(0, 300),
    })),
    matches: Array.from(document.querySelectorAll('*')).map((el, i) => {
      const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
      const r = el.getBoundingClientRect();
      return {
        i, tag: el.tagName, id: el.id || '', cls: String(el.className || ''), txt: txt.slice(0, 160),
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
        rect: {x:r.x,y:r.y,w:r.width,h:r.height},
        html: el.outerHTML.slice(0, 400),
      };
    }).filter(x => x.visible && keys.test([x.id,x.cls,x.txt,x.html].join(' '))).slice(0, 400)
  };
}'''

async def dump(page, outdir: Path, name: str):
    data = await page.evaluate(JS_SCAN)
    await page.screenshot(path=str(outdir / f'{name}.png'), full_page=True)
    (outdir / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data

async def click_visible_text(page, text: str):
    loc = page.get_by_text(text, exact=True)
    cnt = await loc.count()
    for i in range(min(cnt, 8)):
        el = loc.nth(i)
        try:
            if await el.is_visible(timeout=1000):
                try:
                    await el.click(timeout=3000)
                    return f'text:{text}:click'
                except Exception:
                    await el.click(timeout=3000, force=True)
                    return f'text:{text}:force'
        except Exception:
            pass
    return None

async def main():
    outdir = base / 'debug' / 'probe_importdoc_in_article'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_importdoc_article_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(8000)

        # 首页 -> 发布作品
        await page.locator('#home-publish-btn').evaluate("el => el.click()")
        await page.wait_for_timeout(5000)

        # 顶部 -> 图文
        await click_visible_text(page, '图文')
        await page.wait_for_timeout(6000)

        result = {'steps': []}
        result['steps'].append({'stage': 'article_ready', **(await dump(page, outdir, '01_article_ready'))})

        # 点插入：先文本，再 React entry
        how = await click_visible_text(page, '插入')
        if not how:
            loc = page.locator('.FeEditorApp-_4ecaee52b311664f-entry').first
            try:
                await loc.click(timeout=4000)
                how = 'css:entry:click'
            except Exception:
                try:
                    await loc.click(timeout=4000, force=True)
                    how = 'css:entry:force'
                except Exception:
                    pass
        result['steps'].append({'action': 'click_insert', 'how': how, 'url_after': page.url})
        await page.wait_for_timeout(4000)
        result['steps'].append({'stage': 'after_insert_click', **(await dump(page, outdir, '02_after_insert_click'))})

        # 再试直接点“导入文档”文字
        how2 = await click_visible_text(page, '导入文档')
        result['steps'].append({'action': 'click_importdoc', 'how': how2, 'url_after': page.url})
        await page.wait_for_timeout(4000)
        result['steps'].append({'stage': 'after_importdoc_click', **(await dump(page, outdir, '03_after_importdoc_click'))})

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

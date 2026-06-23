from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / 'ck.txt'
ARTICLES = Path(r"C:\Users\Administrator\Desktop\mingming\国际")
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1'

DISMISS = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span'));
  for (const el of els) {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    if (!(r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0)) continue;
    if (t === '我知道了' || t === '下一步' || String(el.className || '').includes('cheetah-tour-close')) {
      if (typeof el.click === 'function') el.click();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
    }
  }
  return true;
}'''

OPEN_INSERT = r'''() => {
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  if (!entry) return false;
  const r = entry.getBoundingClientRect();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  }
  try { entry.click(); } catch (_) {}
  return true;
}'''

CLICK_IMPORT = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const picked = items.find(el => el.querySelector('.l-icon-BjhBasicDaoruwendang')) || items.find(el => /导入文档/.test(textOf(el))) || null;
  if (!picked) return false;
  const r = picked.getBoundingClientRect();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  }
  try { picked.click(); } catch (_) {}
  return true;
}'''

SWITCH_THREE = r'''() => {
  const input = document.querySelector('input.cheetah-radio-input[name="cover"][value="three"]');
  const label = input ? input.closest('label') : null;
  const target = label || input;
  if (!target) return {ok:false};
  const r = target.getBoundingClientRect();
  if (input) {
    input.checked = true;
    input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  }
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  try { target.click(); } catch (_) {}
  return Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked}));
}'''

PROBE = r'''() => {
  const root = document.querySelector('#bjhNewsCover');
  const list = root?.querySelector('.FeEditorApp-_93c3fe2a3121c388-list');
  const items = Array.from(root?.querySelectorAll('.FeEditorApp-_93c3fe2a3121c388-item') || []);
  const dumpNode = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const attrs = {};
    for (const a of Array.from(el.attributes || [])) attrs[a.name] = a.value;
    const reactKeys = Object.keys(el).filter(k => k.startsWith('__reactProps$') || k.startsWith('__reactFiber$') || k.startsWith('__reactEventHandlers$'));
    return {
      tag: el.tagName,
      cls: String(el.className || ''),
      id: el.id || '',
      txt: (el.innerText || el.textContent || '').trim().slice(0,200),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      attrs,
      reactKeys,
      html: (el.outerHTML || '').slice(0,1200),
      children: Array.from(el.children || []).slice(0,20).map(ch => ({
        tag: ch.tagName,
        cls: String(ch.className || ''),
        txt: (ch.innerText || ch.textContent || '').trim().slice(0,120),
        html: (ch.outerHTML || '').slice(0,500)
      }))
    };
  };

  const fileInputs = Array.from(document.querySelectorAll('input[type=file]')).map((el, i) => {
    const r = el.getBoundingClientRect();
    return {i, accept: el.getAttribute('accept') || '', name: el.getAttribute('name') || '', cls: String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, visible: !!(el.offsetWidth||el.offsetHeight||el.getClientRects().length), html:(el.outerHTML||'').slice(0,300)};
  });

  return {
    root: dumpNode(root),
    list: dumpNode(list),
    items: items.map(dumpNode),
    fileInputs,
    visibleMaybeCover: Array.from(document.querySelectorAll('*')).map(el => {
      const t = (el.innerText || el.textContent || '').trim();
      const r = el.getBoundingClientRect();
      return {tag:el.tagName, cls:String(el.className||''), txt:t.slice(0,120), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:(el.outerHTML||'').slice(0,300)};
    }).filter(x => x.rect.w > 10 && x.rect.h > 10 && /封面|图片|上传|本地|图库|裁剪|更换/.test(x.txt + ' ' + x.cls + ' ' + x.html)).slice(0,200)
  };
}'''

async def main():
    outdir = base / 'debug' / 'cover_deep_dom_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_cover_deep_dom_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1400, 'height': 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_function("() => !!document.querySelector('#ueditor_0') && !!document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry, #edui41_state')", timeout=120000)
        await page.wait_for_timeout(7000)
        await page.evaluate(DISMISS)
        await page.wait_for_timeout(1200)
        await page.evaluate(OPEN_INSERT)
        await page.wait_for_timeout(800)
        for _ in range(25):
            ok = await page.evaluate(CLICK_IMPORT)
            if ok:
                break
            await page.wait_for_timeout(200)
        locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
        await locator.set_input_files(str(docx))
        await page.wait_for_timeout(7000)
        await page.evaluate(SWITCH_THREE)
        await page.wait_for_timeout(1500)
        result = await page.evaluate(PROBE)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(outdir / 'probe.png'), full_page=True)
        print(json.dumps({'result_path': str(outdir / 'result.json'), 'item_count': len(result.get('items', [])), 'file_input_count': len(result.get('fileInputs', []))}, ensure_ascii=False))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

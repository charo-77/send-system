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

JS_BEFORE = r'''() => {
  const sel = '[class*="InsertionDrawer"], [id*="InsertionDrawer"], [class*="insertionDrawer"]';
  const beforeEls = Array.from(document.querySelectorAll(sel)).map(el => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, id: el.id, cls: String(el.className||'').slice(0, 150), txt: (el.innerText||'').slice(0, 200), visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0, 500)};
  });
  const dropSel = '[class*="dropdown"]:not([style*="none"]), [class*="popover"]:not([style*="none"]), [class*="drawer"]:not([style*="none"])';
  const dropEls = Array.from(document.querySelectorAll(dropSel)).map(el => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, id: el.id, cls: String(el.className||'').slice(0, 150), txt: (el.innerText||'').slice(0, 200), visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0, 500)};
  });
  return {beforeInsertionEls: beforeEls, beforeDropdownEls: dropEls, count: {insertion: beforeEls.length, dropdown: dropEls.length}};
}'''

JS_AFTER = r'''() => {
  const sel = '[class*="InsertionDrawer"], [id*="InsertionDrawer"], [class*="insertionDrawer"]';
  const afterEls = Array.from(document.querySelectorAll(sel)).map(el => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, id: el.id, cls: String(el.className||'').slice(0, 150), txt: (el.innerText||'').slice(0, 200), visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0, 500)};
  });
  const dropSel = '[class*="dropdown"]:not([style*="none"]), [class*="popover"]:not([style*="none"]), [class*="drawer"]:not([style*="none"])';
  const dropEls = Array.from(document.querySelectorAll(dropSel)).map(el => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, id: el.id, cls: String(el.className||'').slice(0, 150), txt: (el.innerText||'').slice(0, 200), visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0, 500)};
  });
  return {afterInsertionEls: afterEls, afterDropdownEls: dropEls, count: {insertion: afterEls.length, dropdown: dropEls.length}};
}'''

async def main():
    outdir = base / 'debug' / 'insertion_drawer_hunt'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_insdraw_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://baijiahao.baidu.com/", wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(6000)
        await page.evaluate("document.querySelector('#home-publish-btn')?.click()")
        await page.wait_for_timeout(5000)
        try:
            await page.get_by_text('图文', exact=True).first.click(timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(6000)

        result = {'steps': []}

        # Before click - snapshot
        before = await page.evaluate(JS_BEFORE)
        await page.screenshot(path=str(outdir / 'before.png'), full_page=True)
        result['steps'].append({'stage': 'before_click', **before})
        print("Before click - insertion drawer count:", before['count']['insertion'])
        print("Before click - dropdown count:", before['count']['dropdown'])

        # Click edui41_state
        await page.evaluate("document.querySelector('#edui41_state')?.click()")
        await page.wait_for_timeout(1000)
        after1 = await page.evaluate(JS_AFTER)
        await page.screenshot(path=str(outdir / 'after_edui41.png'), full_page=True)
        result['steps'].append({'stage': 'after_edui41', **after1})
        print("After edui41 click - insertion drawer count:", after1['count']['insertion'])
        print("After edui41 click - dropdown count:", after1['count']['dropdown'])

        # Click entry
        await page.evaluate("document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry')?.click()")
        await page.wait_for_timeout(1000)
        after2 = await page.evaluate(JS_AFTER)
        await page.screenshot(path=str(outdir / 'after_entry.png'), full_page=True)
        result['steps'].append({'stage': 'after_entry', **after2})

        # Try mouse coordinate click at entry center
        await page.mouse.click(905, 121)  # center of entry rect
        await page.wait_for_timeout(1000)
        after3 = await page.evaluate(JS_AFTER)
        await page.screenshot(path=str(outdir / 'after_mouse.png'), full_page=True)
        result['steps'].append({'stage': 'after_mouse_coord', **after3})
        print("After mouse coord click - insertion drawer count:", after3['count']['insertion'])

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
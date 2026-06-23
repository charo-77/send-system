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

JS_CLOSE_TOUR = r'''() => {
  // Find and remove ALL tour/mask overlays
  const tourMasks = document.querySelectorAll('.cheetah-tour-mask, [class*="tour-mask"], [class*="cheetah-tour"]');
  const removed = tourMasks.length;
  tourMasks.forEach(el => el.remove());

  // Also try to find any dialog/modal that has "我知道了" text
  const tuwenBtn = Array.from(document.querySelectorAll('div[class*="tour"]')).find(el =>
    el.innerText?.includes('我知道了')
  );
  if (tuwenBtn) {
    tuwenBtn.remove();
    return {removed, foundTourBtn: true};
  }

  return {removed, foundTourBtn: false, tourMaskClasses: Array.from(tourMasks).map(el => el.className)};
}'''

JS_SCAN = r'''() => {
  const inputs = Array.from(document.querySelectorAll('input[type=file]')).map(el => ({
    accept: el.getAttribute('accept'), visible: !!(el.offsetWidth||el.offsetHeight),
    rect: (() => { const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()
  }));
  const dialogs = Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="drawer"], [class*="modal"], [class*="popup"], [class*="dropdown"]')).map(el => {
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, txt: (el.innerText||'').slice(0,100)};
  }).filter(x => x.visible && x.rect.w > 30 && x.rect.h > 20);
  return { inputs: inputs.filter(i => i.visible), dialogs, bodyHasImportDoc: document.body.innerText.includes('导入文档'), bodyHasInsert: document.body.innerText.includes('插入') };
}'''

async def main():
    outdir = base / 'debug' / 'import_doc_success'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_importdoc4_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://baijiahao.baidu.com/", wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(6000)

        result = {'steps': []}

        # Step 1: Navigate to tuwen editor
        await page.evaluate("document.querySelector('#home-publish-btn')?.click()")
        try:
            await page.wait_for_url('**/builder/**', timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(4000)
        try:
            await page.get_by_text('图文', exact=True).first.click(timeout=3000)
        except Exception:
            pass
        try:
            await page.wait_for_url('**/builder/**', timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(6000)

        # Step 2: Remove tour overlay completely
        removed = await page.evaluate(JS_CLOSE_TOUR)
        print("Tour removal:", removed)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(outdir / '01_after_tour_remove.png'), full_page=True)

        # Verify overlay gone
        diag = await page.evaluate(JS_SCAN)
        print("After tour removal:", json.dumps(diag, ensure_ascii=False, indent=2))

        # Step 3: Click 插入 via evaluate
        await page.evaluate("document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry')?.click()")
        await page.wait_for_timeout(2000)

        after_insert = await page.evaluate(JS_SCAN)
        await page.screenshot(path=str(outdir / '02_after_insert.png'), full_page=True)
        result['steps'].append({'stage': 'after_insert', **after_insert})
        print("After insert:", after_insert)

        # Step 4: Click 导入文档
        IMPORT_DOC_SELECTOR = "body > div:nth-child(24) > div > div > div > div > div > div:nth-child(2) > div.FeEditorApp-_9d63bce81e3a0b19-items > div:nth-child(8)"
        await page.evaluate(f"document.querySelector('{IMPORT_DOC_SELECTOR}')?.click()")
        await page.wait_for_timeout(3000)

        after_import = await page.evaluate(JS_SCAN)
        await page.screenshot(path=str(outdir / '03_after_import_doc.png'), full_page=True)
        result['steps'].append({'stage': 'after_import_doc', **after_import})
        print("After import doc click:", after_import)
        for inp in after_import.get('inputs', []):
            print("  INPUT:", inp)

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
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

JS_FIND_MENU = r'''() => {
  const out = {};

  // Find the items container
  const items = document.querySelector('.FeEditorApp-_9d63bce81e3a0b19-items');
  if (!items) {
    // Try alternate class name pattern
    const alts = Array.from(document.querySelectorAll('[class*="9d63bce81e3a0b19-items"]'));
    out.altItemsFound = alts.map(el => ({cls: el.className, parent: el.parentElement?.className, count: el.children.length}));
  }
  out.itemsFound = !!items;
  if (items) {
    out.itemCount = items.children.length;
    out.items = Array.from(items.children).map((el, i) => ({
      i,
      cls: el.className,
      txt: (el.innerText||'').trim(),
      html: el.outerHTML.slice(0, 300)
    }));
    out.itemsParent = items.parentElement?.className;
    out.itemsParentHTML = items.parentElement?.outerHTML?.slice(0, 500);
  }

  // Find import doc item specifically
  const importDoc = document.querySelector('[class*="Daoruwendang"], [class*="9d63bce81e3a0b19-item"]');
  out.importDocFound = !!importDoc;
  if (importDoc) {
    out.importDocHTML = importDoc.outerHTML.slice(0, 400);
    out.importDocRect = (() => { const r=importDoc.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })();
    out.importDocParent = importDoc.parentElement?.className;
    out.importDocParentCount = importDoc.parentElement?.children?.length;
  }

  // Also find any file input that just appeared
  out.fileInputs = Array.from(document.querySelectorAll('input[type=file]')).map(el => ({
    accept: el.getAttribute('accept'),
    id: el.id,
    cls: String(el.className||'').slice(0,80),
    visible: !!(el.offsetWidth||el.offsetHeight),
    html: el.outerHTML.slice(0, 300)
  }));

  return out;
}'''

async def main():
    outdir = base / 'debug' / 'click_import_doc'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_importdoc_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://baijiahao.baidu.com/", wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(6000)

        # Navigate to tuwen editor
        await page.evaluate("document.querySelector('#home-publish-btn')?.click()")
        try:
            await page.wait_for_url('**/builder/**', timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(5000)
        try:
            await page.get_by_text('图文', exact=True).first.click(timeout=3000)
        except Exception:
            pass
        await page.wait_for_url('**/builder/**', timeout=10000)
        await page.wait_for_timeout(6000)

        result = {'steps': []}

        # Before clicking insert
        before = await page.evaluate(JS_FIND_MENU)
        await page.screenshot(path=str(outdir / '01_before.png'), full_page=True)
        result['steps'].append({'stage': 'before_insert', **before})
        print("Items found:", before.get('itemsFound'), "itemCount:", before.get('itemCount'))
        print("Import doc found:", before.get('importDocFound'))

        # Click 插入
        await page.evaluate("document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry')?.click()")
        await page.wait_for_timeout(2000)

        # After clicking insert - look for menu
        after_insert = await page.evaluate(JS_FIND_MENU)
        await page.screenshot(path=str(outdir / '02_after_insert.png'), full_page=True)
        result['steps'].append({'stage': 'after_insert', **after_insert})
        print("Items found:", after_insert.get('itemsFound'), "itemCount:", after_insert.get('itemCount'))
        print("Import doc found:", after_insert.get('importDocFound'))
        if after_insert.get('items'):
            print("Menu items:", [it['txt'] for it in after_insert['items']])

        # Click 导入文档
        import_doc_item = page.locator('.FeEditorApp-_9d63bce81e3a0b19-item').filter(has_text='导入文档')
        if await import_doc_item.count() > 0:
            await import_doc_item.first.click(timeout=5000)
            await page.wait_for_timeout(3000)
            after_import = await page.evaluate(JS_FIND_MENU)
            await page.screenshot(path=str(outdir / '03_after_import_doc.png'), full_page=True)
            result['steps'].append({'stage': 'after_import_doc', 'clicked': True, **after_import})
            print("After import doc click - file inputs:", len(after_import.get('fileInputs', [])))
            # Check for dialog/drawer/popup
            print("Import doc found:", after_import.get('importDocFound'))
        else:
            result['steps'].append({'stage': 'after_insert', 'import_doc_clicked': False, 'reason': 'import_doc_item not found in DOM'})
            print("Import doc item NOT found in DOM after insert click!")

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
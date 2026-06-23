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

JS_PROBE = r'''() => {
  // Check what's at the items selector AFTER insert click
  const sel = '.FeEditorApp-_9d63bce81e3a0b19-items';
  const items = document.querySelector(sel);
  const parent = items?.parentElement;
  const grandParent = parent?.parentElement;

  return {
    itemsFound: !!items,
    itemCount: items?.children?.length,
    itemTexts: items ? Array.from(items.children).map(el => el.innerText?.trim()) : [],
    parentCls: parent?.className,
    grandParentCls: grandParent?.className,
    parentHTML: parent?.outerHTML?.slice(0, 400),
    // Also check all visible dialogs/dropdowns
    bodyHasImportDoc: document.body.innerText.includes('导入文档'),
    bodyHasInsert: document.body.innerText.includes('插入'),
    visibleDialogs: Array.from(document.querySelectorAll('[role=dialog], [class*="dropdown"], [class*="popover"], [class*="drawer"]')).map(el => {
      const r = el.getBoundingClientRect();
      return {tag: el.tagName, cls: String(el.className||'').slice(0,80), visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, txt: (el.innerText||'').slice(0,80)};
    }).filter(x => x.visible && x.rect.w > 50 && x.rect.h > 30),
    // Check the exact item at index 8 in items container
    item8HTML: items?.children?.[7]?.outerHTML?.slice(0, 300),
    item8Text: items?.children?.[7]?.innerText?.trim(),
  };
}'''

JS_WAIT_ITEMS = r'''() => {
  const sel = '.FeEditorApp-_9d63bce81e3a0b19-items';
  const items = document.querySelector(sel);
  if (!items) return {found: false};

  return {
    found: true,
    itemCount: items.children.length,
    texts: Array.from(items.children).map(el => el.innerText?.trim()),
    allHTML: items.innerHTML.slice(0, 3000)
  };
}'''

async def main():
    outdir = base / 'debug' / 'probe_items_menu'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_probeitems_{int(time.time())}'),
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

        # Navigate to tuwen editor
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

        # Remove tour overlay
        await page.evaluate("""
          document.querySelectorAll('.cheetah-tour-mask, [class*="tour-mask"]').forEach(el => el.remove());
        """)
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(outdir / '01_editor_clean.png'), full_page=True)

        # Click 插入
        await page.evaluate("document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry')?.click()")

        # IMMEDIATELY probe what exists at the items selector
        for round in range(20):
            probe = await page.evaluate(JS_PROBE)
            if probe['itemsFound'] or probe['bodyHasImportDoc']:
                await page.screenshot(path=str(outdir / f'02_round_{round}.png'), full_page=True)
                print(f"Round {round}: itemsFound={probe['itemsFound']}, itemCount={probe.get('itemCount')}, hasImportDoc={probe['bodyHasImportDoc']}, texts={probe.get('itemTexts')}")
                if probe['itemsFound'] and probe.get('itemCount', 0) > 0:
                    break
            await page.wait_for_timeout(200)

        result['probe'] = probe
        print("Final probe:", json.dumps(probe, ensure_ascii=False, indent=2))

        # If items found, click the import doc item
        if probe.get('itemsFound') and probe.get('itemCount', 0) > 0:
            # Find index of 导入文档
            texts = probe.get('itemTexts', [])
            import_idx = next((i for i, t in enumerate(texts) if '导入文档' in t), None)
            print(f"导入文档 found at index: {import_idx}")

            # Click by exact selector or by index
            if import_idx is not None:
                # Try clicking the specific item
                await page.evaluate(f"""
                  const items = document.querySelector('.FeEditorApp-_9d63bce81e3a0b19-items');
                  items?.children?.[{import_idx}]?.click();
                """)
                await page.wait_for_timeout(3000)

                after = await page.evaluate(JS_PROBE)
                await page.screenshot(path=str(outdir / '03_after_import_click.png'), full_page=True)
                print("After clicking import doc:", json.dumps({
                    'bodyHasImportDoc': after.get('bodyHasImportDoc'),
                    'inputs': len(after.get('visibleDialogs', [])),
                    'dialogs': after.get('visibleDialogs', [])
                }, ensure_ascii=False, indent=2))
                result['after_import'] = after
        else:
            print("Items container NEVER appeared after clicking insert!")
            print("bodyHasImportDoc:", probe.get('bodyHasImportDoc'))
            result['items_never_appeared'] = True

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
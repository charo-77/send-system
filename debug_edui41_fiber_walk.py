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

# JS to walk up the fiber tree from edui41 to find its React component
JS_FIBER_WALK = r'''() => {
  const out = {};
  const el = document.querySelector('#edui41_state');
  if (!el) return { error: 'edui41_state not found' };

  // Find all react keys
  const allKeys = Object.keys(el).filter(k => k.includes('react') || k.includes('React') || k.includes('fiber'));
  out.reactKeys = allKeys;

  // Get fiber
  const fiberKey = allKeys.find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternals'));
  let fiber = fiberKey ? el[fiberKey] : null;
  if (!fiber) return { reactKeys: allKeys, error: 'no fiber found' };

  out.foundFiber = true;
  out.fiberTag = fiber.tag;
  out.fiberType = String(fiber.elementType).slice(0, 150);

  // Walk up to find the React component that manages insertion/drawer
  let current = fiber;
  const path = [];
  for (let i = 0; i < 20 && current; i++) {
    path.push({
      level: i,
      tag: current.tag,
      type: current.elementType ? String(current.elementType).slice(0, 100) : null,
      typeDisplay: current.elementType?.displayName || current.elementType?.name || null,
      memoizedProps: current.memoizedProps ? Object.keys(current.memoizedProps).slice(0, 30) : null,
      pendingProps: current.pendingProps ? Object.keys(current.pendingProps).slice(0, 30) : null,
      memoizedState: current.memoizedState ? Object.keys(current.memoizedState).slice(0, 30) : null,
      flags: current.flags,
      subtreeFlags: current.subtreeFlags,
    });
    current = current.return;
  }
  out.path = path;

  // Also check the fiber for any 'click' or 'open' or 'insert' or 'drawer' in the entire tree
  const methods = [];
  current = fiber;
  for (let i = 0; i < 30 && current; i++) {
    try {
      const proto = Object.getPrototypeOf(current);
      if (proto) {
        const ownMethods = Object.getOwnPropertyNames(proto).filter(k => /show|open|click|insert|drawer|popup|menu|setState|dispatch|handle|onClick|onMouse/i.test(k));
        if (ownMethods.length) methods.push({level: i, methods: ownMethods});
      }
    } catch(e) {}
    current = current.return;
  }
  out.methods = methods;

  return out;
}'''

# JS to do fast polling after click - observe edui42 and body
JS_POLL = r'''() => {
  const out = { observations: [] };
  const seen = new Set();

  for (let round = 0; round < 10; round++) {
    const snap = {
      round,
      edui42_style: null,
      edui42_childCount: 0,
      edui42_text: '',
      body_import_doc: document.body.innerText.includes('导入文档'),
      body_insertion_drawer: !!document.querySelector('[class*="InsertionDrawer"], [id*="InsertionDrawer"], [class*="insertionDrawer"]'),
      body_dropdown: !!document.querySelector('[class*="dropdown"]:not([style*="none"]), [class*="popover"]:not([style*="none"]), [class*="drawer"]:not([style*="none"])'),
      file_inputs: Array.from(document.querySelectorAll('input[type=file]')).map(el => ({
        accept: el.getAttribute('accept'), id: el.id, cls: String(el.className||'').slice(0,50),
        visible: !!(el.offsetWidth || el.offsetHeight)
      })),
    };

    const edui42 = document.querySelector('#edui42');
    if (edui42) {
      snap.edui42_style = edui42.getAttribute('style');
      const content = document.querySelector('#edui42_content');
      if (content) {
        snap.edui42_childCount = content.children.length;
        snap.edui42_text = (content.innerText || '').slice(0, 200);
      }
    }

    const key = JSON.stringify(snap);
    if (!seen.has(key)) {
      seen.add(key);
      out.observations.push(snap);
    }
  }

  out.observations = out.observations.slice(0, 5);
  return out;
}'''

async def main():
    outdir = base / 'debug' / 'edui41_fiber_walk'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_edui41_{int(time.time())}'),
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
        await page.wait_for_timeout(5000)
        try:
            await page.get_by_text('图文', exact=True).first.click(timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(6000)

        # Probe fiber structure
        fiber_info = await page.evaluate(JS_FIBER_WALK)
        (outdir / 'fiber_walk.json').write_text(json.dumps(fiber_info, ensure_ascii=False, indent=2), encoding='utf-8')
        print("Fiber info:", json.dumps(fiber_info, ensure_ascii=False, indent=2))
        await page.screenshot(path=str(outdir / 'before.png'), full_page=True)

        # Try clicking edui41_state (the UE element that wraps the React entry)
        print("Clicking edui41_state via DOM...")
        await page.evaluate("document.querySelector('#edui41_state')?.click()")
        await page.wait_for_timeout(500)

        # Now poll rapidly 10 times
        poll_result = await page.evaluate(JS_POLL)
        await page.screenshot(path=str(outdir / 'after_edui41_click.png'), full_page=True)
        (outdir / 'poll_after_edui41.json').write_text(json.dumps(poll_result, ensure_ascii=False, indent=2), encoding='utf-8')
        print("Poll after edui41 click:", json.dumps(poll_result, ensure_ascii=False, indent=2))

        # Also try clicking the React entry
        await page.evaluate("document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry')?.click()")
        await page.wait_for_timeout(500)
        poll2 = await page.evaluate(JS_POLL)
        (outdir / 'poll_after_entry.json').write_text(json.dumps(poll2, ensure_ascii=False, indent=2), encoding='utf-8')
        print("Poll after entry click:", json.dumps(poll2, ensure_ascii=False, indent=2))

        # Also try pointer events (React uses pointer events on this element)
        await page.evaluate("""
          const el = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry');
          if (el) {
            el.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, cancelable: true, view: window}));
            el.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, cancelable: true, view: window}));
          }
        """)
        await page.wait_for_timeout(500)
        poll3 = await page.evaluate(JS_POLL)
        (outdir / 'poll_after_pointer.json').write_text(json.dumps(poll3, ensure_ascii=False, indent=2), encoding='utf-8')
        print("Poll after pointer events:", json.dumps(poll3, ensure_ascii=False, indent=2))

        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
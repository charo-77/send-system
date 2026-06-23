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
URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"

JS_PROBE = r'''() => {
  const out = { actions: [] };

  // Find the entry node
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry');
  if (!entry) {
    return { error: 'entry not found' };
  }

  out.entryFound = true;

  // Try multiple fiber keys
  const fiberKeys = ['__reactFiber', '__reactFiber$', '__reactInternalInstance', '__reactInternals'];
  const propKeys = ['__reactProps', '__reactProps$'];
  let fiber = null;
  let props = null;

  for (const k of fiberKeys) {
    if (entry[k]) { fiber = entry[k]; out.fiberKey = k; break; }
  }
  for (const k of propKeys) {
    if (entry[k]) { props = entry[k]; out.propsKey = k; break; }
  }

  if (!fiber) {
    // fallback: search all keys on the element
    const allKeys = Object.keys(entry).filter(k => k.startsWith('__react') || k.startsWith('react'));
    out.allReactKeys = allKeys.slice(0, 20);
  }

  out.fiberInfo = fiber ? {
    debugDisplayName: fiber.debugDisplayName,
    elementType: String(fiber.elementType),
    stateNode: !!fiber.stateNode,
    memoizedProps: fiber.memoizedProps ? Object.keys(fiber.memoizedProps).slice(0, 30) : null,
    memoizedState: fiber.memoizedState ? Object.keys(fiber.memoizedState).slice(0, 30) : null,
    pendingProps: fiber.pendingProps ? Object.keys(fiber.pendingProps).slice(0, 30) : null,
  } : null;

  out.propsInfo = props ? {
    keys: Object.keys(props).slice(0, 30),
    onClick: typeof props.onClick === 'function' ? 'FUNCTION_EXISTS' : typeof props.onClick,
  } : null;

  // Try finding the parent toolbar/dropdown that might control this
  const toolbar = document.querySelector('.edui-toolbar, #edui2, .FeEditorApp-_4ecaee52b311664f-entry')?.closest('[class*="toolbar"], [class*="slotbox"], [class*="insert"]');
  out.toolbar = toolbar ? {
    cls: toolbar.className,
    id: toolbar.id,
    keys: Object.keys(toolbar).filter(k => k.startsWith('__react')).slice(0, 10)
  } : null;

  // Try internal $EDITORUI_V2 edui41
  const ed41 = window['$' + 'EDITORUI_V2']?.edui41;
  if (ed41) {
    const proto = Object.getPrototypeOf(ed41);
    out.edui41Methods = proto ? Object.getOwnPropertyNames(proto).filter(k => /show|popup|render|attach|open|toggle|click|trigger/i.test(k)) : [];
  }

  // Try: directly call React's onClick by dispatching a proper React event
  // First, find the root react fiber
  let rootFiber = fiber;
  while (rootFiber && rootFiber.return) rootFiber = rootFiber.return;
  out.rootFiberInfo = rootFiber ? {
    tag: rootFiber.tag,
    stateNode: !!rootFiber.stateNode,
    memoizedProps: rootFiber.memoizedProps ? Object.keys(rootFiber.memoizedProps).slice(0, 20) : null,
  } : null;

  // Try to find any drawer/popup/dropdown in portal-root that might be the insertion menu
  const portalRoot = document.querySelector('#portal-root, [class*="portal-root"]');
  out.portalRootFound = !!portalRoot;
  if (portalRoot) {
    out.portalChildren = Array.from(portalRoot.querySelectorAll('*')).slice(0, 50).map(el => ({
      tag: el.tagName, cls: String(el.className||'').slice(0,100), txt: (el.innerText||'').slice(0,80), html: el.outerHTML.slice(0,200)
    }));
  }

  // Try calling the entry's click via React synthetic event
  try {
    const syntheticEvent = new MouseEvent('click', { bubbles: true, cancelable: true, view: window });
    entry.dispatchEvent(syntheticEvent);
    out.dispatchEventOk = true;
  } catch(e) {
    out.dispatchEventErr = String(e);
  }

  return out;
}'''

async def main():
    outdir = base / 'debug' / 'react_fiber_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_fiber_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://baijiahao.baidu.com/", wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(6000)

        # Click publish button
        await page.evaluate("document.querySelector('#home-publish-btn')?.click()")
        await page.wait_for_timeout(5000)

        # Click 图文
        loc = page.get_by_text('图文', exact=True)
        if await loc.count():
            await loc.first.click(timeout=3000)
        await page.wait_for_timeout(6000)

        result = await page.evaluate(JS_PROBE)
        await page.screenshot(path=str(outdir / 'editor.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
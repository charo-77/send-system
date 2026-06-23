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

JS_DEEP = r'''() => {
  const out = {};

  // Get the entry element
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry');
  if (!entry) return { error: 'entry not found' };

  // Find ALL keys on the element that contain 'react'
  const allKeys = Object.keys(entry).filter(k => k.includes('react') || k.includes('React') || k.includes('fiber') || k.includes('Fiber'));
  out.allReactKeys = allKeys;

  // For each react key, try to get the value
  for (const k of allKeys) {
    try {
      const val = entry[k];
      if (val && typeof val === 'object') {
        // It's a fiber-like object
        out[k] = {
          type: typeof val,
          keys: Object.keys(val).slice(0, 30),
          // Try getting key props
          memoizedProps: val.memoizedProps ? JSON.stringify(val.memoizedProps).slice(0, 300) : null,
          pendingProps: val.pendingProps ? JSON.stringify(val.pendingProps).slice(0, 300) : null,
          memoizedState: val.memoizedState ? JSON.stringify(val.memoizedState).slice(0, 300) : null,
          elementType: val.elementType ? String(val.elementType).slice(0, 100) : null,
          tag: val.tag,
          effectTag: val.effectTag,
          // Walk up the fiber tree
          return_type: val.return ? String(val.return.elementType).slice(0, 100) : null,
          return_return_type: val.return?.return ? String(val.return.return.elementType).slice(0, 100) : null,
          // Key method names on the fiber (these are actual methods)
          ownKeys: Object.getOwnPropertyNames(Object.getPrototypeOf(val)).filter(k => /show|popup|menu|click|open|dispatch|toggle|setState|render|commit/i.test(k)).slice(0, 30),
        };
      } else if (typeof val === 'function') {
        out[k] = { type: 'function', name: val.name };
      }
    } catch(e) {
      out[k] = { error: String(e) };
    }
  }

  // Also check the DOM element itself - get ALL of its properties using descriptors
  const ownDescriptors = {};
  for (const k of allKeys.slice(0, 5)) {
    try {
      const desc = Object.getOwnPropertyDescriptor(entry, k);
      if (desc) {
        out['desc_' + k] = {
          value: desc.value ? (typeof desc.value === 'object' ? JSON.stringify(desc.value).slice(0, 200) : String(desc.value).slice(0, 100)) : null,
          get: typeof desc.get === 'function' ? desc.get.toString().slice(0, 100) : null,
        };
      }
    } catch(e) {}
  }

  // Walk up the DOM tree to find what controls insertion
  let dom = entry;
  for (let i = 0; i < 5 && dom; i++) {
    dom = dom.parentElement;
    if (dom) {
      const parentKeys = Object.keys(dom).filter(k => k.includes('react') || k.includes('Fiber'));
      if (parentKeys.length) {
        out['parent_' + i] = {
          tag: dom.tagName,
          cls: dom.className?.slice(0, 80),
          id: dom.id,
          reactKeys: parentKeys,
        };
      }
    }
  }

  // Now: check if clicking the arrow part (not just the entry) makes a difference
  const arrow = document.querySelector('.FeEditorApp-_4ecaee52b311664f-arrow');
  out.arrowFound = !!arrow;
  if (arrow) {
    out.arrowRect = arrow.getBoundingClientRect();
    out.entryRect = entry.getBoundingClientRect();
  }

  // Check for any newly appearing elements in body after a click
  out.bodyChildrenBeforeClick = Array.from(document.body.children).map(el => ({
    tag: el.tagName, id: el.id, cls: String(el.className||'').slice(0,100),
    visible: !!(el.offsetWidth || el.offsetHeight),
    rect: (() => { const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()
  })).filter(x => x.visible && x.rect.w > 50 && x.rect.h > 50);

  return out;
}'''

JS_CLICK_RESULT = r'''() => {
  const out = {};

  // Get all elements that just appeared (visible, in body, weren't there before or changed)
  const bodyEls = Array.from(document.body.querySelectorAll('*')).map(el => {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName, id: el.id || '', cls: String(el.className||'').slice(0, 100),
      txt: (el.innerText||'').slice(0, 100),
      html: el.outerHTML.slice(0, 300),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x, y:r.y, w:r.width, h:r.height}
    };
  }).filter(x => x.visible && x.rect.w > 30 && x.rect.h > 20);

  // Look for: dropdown, popup, drawer, menu, portal
  out.matching = bodyEls.filter(x =>
    /dropdown|popup|drawer|menu|portal|插入|导入|文档|word|doc/i.test([x.id, x.cls, x.txt, x.html].join(' '))
  ).slice(0, 50);

  // Check edui42
  const edui42 = document.querySelector('#edui42');
  out.edui42 = edui42 ? {
    style: edui42.getAttribute('style'),
    cls: edui42.className,
    rect: (() => { const r=edui42.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })(),
    html: edui42.outerHTML.slice(0, 800)
  } : null;

  // Check portal root children count
  const portal = document.querySelector('#portal-root');
  out.portalChildrenCount = portal ? portal.children.length : -1;

  // Look for any visible element containing 导入 or 文档
  out.importDocEls = bodyEls.filter(x => /导入文档|导入.word|word导入|doc导入/i.test(x.txt)).slice(0, 20);

  return out;
}'''

async def main():
    outdir = base / 'debug' / 'fiber_deep_dive'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_fiber2_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://baijiahao.baidu.com/", wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(6000)

        # Home -> publish -> tuwen
        await page.evaluate("document.querySelector('#home-publish-btn')?.click()")
        await page.wait_for_timeout(5000)
        try:
            await page.get_by_text('图文', exact=True).first.click(timeout=3000)
        except Exception:
            pass
        await page.wait_for_timeout(6000)

        # Step 1: Probe before click
        before = await page.evaluate(JS_DEEP)
        await page.screenshot(path=str(outdir / 'before_click.png'), full_page=True)
        (outdir / 'before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
        print("Before:", json.dumps({k: str(v)[:100] for k, v in before.items()}, ensure_ascii=False))

        # Step 2: Click the entry element
        entry = page.locator('.FeEditorApp-_4ecaee52b311664f-entry')
        if await entry.count():
            await entry.evaluate("el => el.click()")
        await page.wait_for_timeout(2000)

        # Step 3: Check result after click
        after_click = await page.evaluate(JS_CLICK_RESULT)
        await page.screenshot(path=str(outdir / 'after_click.png'), full_page=True)
        (outdir / 'after_click.json').write_text(json.dumps(after_click, ensure_ascii=False, indent=2), encoding='utf-8')
        print("After click matching:", len(after_click.get('matching', [])))
        print("edui42:", json.dumps(after_click.get('edui42', {}), ensure_ascii=False, indent=2).slice(0, 300))
        print("Import doc els:", len(after_click.get('importDocEls', [])))

        # Step 4: Try arrow click too
        arrow = page.locator('.FeEditorApp-_4ecaee52b311664f-arrow')
        if await arrow.count():
            await arrow.evaluate("el => el.click()")
            await page.wait_for_timeout(2000)
            arrow_after = await page.evaluate(JS_CLICK_RESULT)
            await page.screenshot(path=str(outdir / 'after_arrow_click.png'), full_page=True)
            print("After arrow click matching:", len(arrow_after.get('matching', [])))

        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
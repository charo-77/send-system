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

JS_CLICK_INSERT = r'''() => {
  // Click 插入 and immediately check what appears
  const insertEl = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry');
  if (!insertEl) return {error: 'insert not found'};
  insertEl.click();

  // Probe at t=0 (synchronously after click)
  return {
    t0_itemsFound: !!document.querySelector('.FeEditorApp-_9d63bce81e3a0b19-items'),
    t0_bodyHasImportDoc: document.body.innerText.includes('导入文档'),
    t0_visibleItems: Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item')).map(el => el.innerText?.trim()),
    t0_parentHTML: document.querySelector('.FeEditorApp-_9d63bce81e3a0b19-items')?.parentElement?.outerHTML?.slice(0, 600),
    t0_popover: Array.from(document.querySelectorAll('[class*="dropdown"], [class*="popover"], [class*="drawer"], [class*="menu"]')).map(el => {
      const r = el.getBoundingClientRect();
      return {cls: el.className, visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, txt: (el.innerText||'').slice(0,80)};
    }).filter(x => x.visible && x.rect.w > 30 && x.rect.h > 20),
  };
}'''

JS_POLL_LONG = r'''() => {
  const results = [];
  for (let i = 0; i < 50; i++) {
    const snap = {
      t: i * 100,
      itemsFound: !!document.querySelector('.FeEditorApp-_9d63bce81e3a0b19-items'),
      itemCount: document.querySelector('.FeEditorApp-_9d63bce81e3a0b19-items')?.children?.length,
      bodyHasImportDoc: document.body.innerText.includes('导入文档'),
      visiblePopovers: Array.from(document.querySelectorAll('[class*="dropdown"], [class*="popover"], [class*="drawer"]')).map(el => {
        const r = el.getBoundingClientRect();
        return {cls: el.className, visible: !!(el.offsetWidth||el.offsetHeight), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, txt: (el.innerText||'').slice(0,80)};
      }).filter(x => x.visible && x.rect.w > 30 && x.rect.h > 20),
    };
    if (snap.itemsFound || snap.bodyHasImportDoc || snap.visiblePopovers.length > 0) {
      results.push(snap);
      if (results.length >= 5) break;
    }
  }
  return results;
}'''

async def main():
    outdir = base / 'debug' / 'click_insert_timing'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_timing_{int(time.time())}'),
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

        # Close popover first
        await page.evaluate("""
          const btns = document.querySelectorAll('div[class*="popover"]');
          btns.forEach(el => {
            if (el.innerText?.includes('我知道了')) {
              const closeBtn = Array.from(el.querySelectorAll('*')).find(x => x.innerText?.includes('我知道了'));
              closeBtn?.click();
            }
          });
          document.querySelectorAll('.cheetah-tour-mask').forEach(el => el.remove());
        """)
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(outdir / '01_clean.png'), full_page=True)

        # Click insert and immediately poll
        t0_result = await page.evaluate(JS_CLICK_INSERT)
        result['t0'] = t0_result
        print("T0 result:", json.dumps(t0_result, ensure_ascii=False, indent=2))
        await page.screenshot(path=str(outdir / '02_t0.png'), full_page=True)

        # Now do long polling
        poll_result = await page.evaluate(JS_POLL_LONG)
        result['poll'] = poll_result
        print("Poll results:", json.dumps(poll_result, ensure_ascii=False, indent=2))
        await page.screenshot(path=str(outdir / '03_poll_end.png'), full_page=True)

        # If still nothing, try clicking edui41_state (UE handler)
        if not any(r.get('itemsFound') or r.get('bodyHasImportDoc') for r in poll_result):
            print("Items still not found - trying edui41_state click via UE handler")
            await page.evaluate("""
              const el = document.getElementById('edui41_state');
              if (el) {
                const rect = el.getBoundingClientRect();
                const evt = new MouseEvent('click', {
                  bubbles: true, cancelable: true, view: window,
                  clientX: rect.x + rect.width/2, clientY: rect.y + rect.height/2
                });
                el.dispatchEvent(evt);
              }
            """)
            poll_result2 = await page.evaluate(JS_POLL_LONG)
            result['poll_ue_handler'] = poll_result2
            print("Poll after UE handler:", json.dumps(poll_result2, ensure_ascii=False, indent=2))
            await page.screenshot(path=str(outdir / '04_after_ue.png'), full_page=True)

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())
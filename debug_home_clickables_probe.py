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

JS = r'''() => {
  const sels = 'a,button,[role=button],input[type=button],input[type=submit],div,span';
  return Array.from(document.querySelectorAll(sels)).map((el, i) => {
    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const clickable = el.tagName === 'A' || el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || cs.cursor === 'pointer' || !!el.onclick || !!el.closest('a,button,[role=button]');
    return {
      i,
      tag: el.tagName,
      id: el.id || '',
      cls: String(el.className || ''),
      txt: txt.slice(0, 200),
      href: el.getAttribute('href'),
      onclick: !!el.onclick,
      cursor: cs.cursor,
      clickable: !!clickable,
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: el.outerHTML.slice(0, 400),
    };
  }).filter(x => x.visible && (x.clickable || /发布|创作|图文|文章|视频|动态|直播|作品/i.test([x.txt,x.id,x.cls,x.html].join(' ')))).slice(0, 500)
}'''

async def main():
    outdir = base / 'debug' / 'home_clickables_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_home_probe_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(8000)
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        data = await page.evaluate(JS)
        body = await page.locator('body').inner_text(timeout=5000)
        await page.screenshot(path=str(outdir / 'home.png'), full_page=True)
        payload = {'url': page.url, 'title': await page.title(), 'body_prefix': body[:5000], 'items': data}
        (outdir / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

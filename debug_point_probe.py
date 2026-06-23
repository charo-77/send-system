from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

async def main():
    outdir = base / 'debug' / 'point_probe'; outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(base / 'ck.txt')
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(base / 'edge_profile_point_probe'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(15000)
        pts = []
        for y in [90,110,130,150,170,190,210,240,270,300,340,380,430,500,600,750,850]:
            for x in [100,140,180,260,420,760,900]:
                pts.append({'x':x,'y':y})
        data = await page.evaluate("""pts => pts.map(p => {
            const stack = document.elementsFromPoint(p.x,p.y).slice(0,8).map(el => {
                const r = el.getBoundingClientRect();
                return {tag: el.tagName, id: el.id || '', cls: String(el.className || '').slice(0,120), txt: (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,80), ce: el.getAttribute('contenteditable'), isCE: el.isContentEditable, role: el.getAttribute('role'), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
            });
            return {...p, stack};
        })""", pts)
        (outdir/'points.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(outdir/'page.png'), full_page=True)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__': asyncio.run(main())

from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(r'D:\milu_publish_reverse_20260513')
sys.path.insert(0, str(BASE / 'src'))

from cookies import load_cookie_file
from browser_publish import inject_cookies, select_activities

CK = BASE / 'ck.txt'
PROFILE = BASE / 'edge_profile_activity_hold_20260525'
DEBUG_DIR = BASE / 'debug' / 'activity_hold_20260525_1636'
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=events&is_from_cms=1'

async def main():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        str(PROFILE),
        channel='msedge',
        headless=False,
        viewport={'width': 1440, 'height': 960},
        args=['--disable-blink-features=AutomationControlled'],
    )
    injected = await inject_cookies(context, cookies)
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(8000)
    before = await page.evaluate("""() => ({url: location.href, title: document.title, body: (document.body.innerText || '').slice(0, 5000)})""")
    result = await select_activities(page, ['AI文史百工中国'])
    await page.wait_for_timeout(1500)
    after = await page.evaluate("""() => ({url: location.href, title: document.title, body: (document.body.innerText || '').slice(0, 5000)})""")
    out = {
        'cookies_injected': injected,
        'before': before,
        'activity': result,
        'after': after,
    }
    (DEBUG_DIR / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(DEBUG_DIR / 'after.png'), full_page=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print('HOLDING_BROWSER_OPEN')
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())

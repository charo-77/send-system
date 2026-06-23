from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

SAMPLE = '这是一次正文输入测试。\n第二段测试。\n第三段测试。' * 8

async def main() -> None:
    outdir = base / "debug" / "fill_military_body_type2"
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513\ck.txt"))

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_fill_body_type2_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        frame_el = await page.wait_for_selector('iframe#ueditor_0', timeout=30000)
        frame = await frame_el.content_frame()
        await frame.wait_for_load_state('domcontentloaded', timeout=30000)
        body = frame.locator('body').first
        await body.click(force=True)
        await body.press('Control+A')
        await body.press('Backspace')
        await body.type(SAMPLE, delay=5)
        await page.wait_for_timeout(3000)
        info = await body.evaluate("""el => ({
            textPrefix: (el.innerText || '').slice(0, 300),
            htmlPrefix: (el.innerHTML || '').slice(0, 500),
            textLength: (el.innerText || '').length,
            imgCount: el.querySelectorAll('img').length,
        })""")
        count_text = await page.locator('#editWorldCount .count').inner_text(timeout=3000)
        await page.screenshot(path=str(outdir / 'after_type2.png'), full_page=True)
        data = {"count_text": count_text, "info": info, "url": page.url}
        (outdir / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

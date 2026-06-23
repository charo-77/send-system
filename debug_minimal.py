"""
debug_minimal.py - 最小化测试：只获取页面 title
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))
from cookies import load_cookie_file as load_cookies
from browser_publish import inject_cookies as inject_cookies_func

PUBLISH_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"
PROJECT_DIR = Path(__file__).parent


async def main():
    print("[1] Starting")
    cookie_path = PROJECT_DIR / "ck.txt"
    cookies = load_cookies(cookie_path)
    print(f"[2] Cookies loaded: {len(cookies)}")

    async with async_playwright() as p:
        print("[3] Launching browser")
        context = await p.chromium.launch_persistent_context(
            str(PROJECT_DIR / "bjh_browser_data"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        print("[4] Browser launched")
        await inject_cookies_func(context, cookies)
        print("[5] Cookies injected")

        page = context.pages[0] if context.pages else await context.new_page()
        print(f"[6] Page ready, url={page.url}")

        print("[7] Navigating...")
        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
        print(f"[8] Navigated, url={page.url}")

        # Simple title check
        title = await page.title()
        print(f"[9] Title: {title}")

        # Check body text
        body_text = await page.evaluate("document.body.innerText")
        print(f"[10] Body text length: {len(body_text)}")
        print(f"[11] Body text sample: {body_text[:200]}")

        await page.screenshot(path=str(PROJECT_DIR / "debug" / "minimal.png"))
        print("[12] Screenshot saved")

        await context.close()

    print("[DONE]")


if __name__ == "__main__":
    asyncio.run(main())
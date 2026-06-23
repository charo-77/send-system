"""
debug_cdp_error.py
测试 CDP session 是否正常工作
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))
from cookies import load_cookie_file as load_cookies
from browser_publish import inject_cookies as inject_cookies_func

PROJECT_DIR = Path(__file__).parent
DEBUG_DIR = PROJECT_DIR / "debug" / "cdp_error_test"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    cookie_path = PROJECT_DIR / "ck.txt"
    cookies = load_cookies(cookie_path)
    print(f"[COOKIES] loaded {len(cookies)} items")

    PUBLISH_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROJECT_DIR / "bjh_browser_data"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies_func(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        for text in ["我知道了", "下一步", "取消"]:
            try:
                btn = page.get_by_text(text, exact=False).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        await page.wait_for_selector("#ueditor", timeout=30000)
        await page.wait_for_selector("iframe#ueditor_0", timeout=30000)
        await page.wait_for_timeout(3000)
        print("[PAGE] editor ready, getting CDP session")

        cdp = await context.new_cdp_session(page)
        print(f"[CDP] session created: {cdp}")

        # 简单测试：获取页面 title
        try:
            title_result = await cdp.send("Runtime.evaluate", {
                "expression": "document.title"
            })
            print(f"[CDP] title_result: {json.dumps(title_result, ensure_ascii=False)}")
        except Exception as e:
            print(f"[CDP] title error: {e}")

        # 检查 page URL
        print(f"[PAGE] url: {page.url}")

        # 用 page.evaluate 测试普通 JS
        try:
            plain_result = await page.evaluate("document.title")
            print(f"[PAGE evaluate] title: {plain_result}")
        except Exception as e:
            print(f"[PAGE evaluate] error: {e}")

        # 检查 $EDITORUI_V2
        try:
            editor_result = await page.evaluate("(function(){return typeof $EDITORUI_V2;})()")
            print(f"[PAGE] $EDITORUI_V2 type: {editor_result}")
        except Exception as e:
            print(f"[PAGE] $EDITORUI_V2 error: {e}")

        # 检查 edui41_state
        try:
            el_result = await page.evaluate("(function(){var el=document.getElementById('edui41_state');return el?{id:el.id,text:el.innerText.trim()}:null;})()")
            print(f"[PAGE] edui41_state: {el_result}")
        except Exception as e:
            print(f"[PAGE] edui41_state error: {e}")

        await page.screenshot(path=str(DEBUG_DIR / "test.png"), full_page=True)
        print(f"[SCREENSHOT] saved")

        await context.close()

    print("[DONE]")


if __name__ == "__main__":
    asyncio.run(main())
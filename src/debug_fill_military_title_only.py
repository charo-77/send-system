from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import extract_docx_article, list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

ARTICLE_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\军事")

async def main() -> None:
    outdir = base / "debug" / "fill_military_title_only"
    outdir.mkdir(parents=True, exist_ok=True)
    files = list_docx(ARTICLE_DIR)
    article = extract_docx_article(files[0])
    title_text = (article.title or '').strip()[:64].rstrip()
    cookies = load_cookie_file(Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513\ck.txt"))

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_fill_title_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(outdir / "before_title.png"), full_page=True)
        sel = '[data-testid="news-title-input"] [contenteditable="true"][data-lexical-editor="true"]'
        loc = page.locator(sel).first
        await loc.wait_for(timeout=30000)
        await loc.evaluate("""el => { el.focus(); const range = document.createRange(); range.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }""")
        await page.keyboard.press('Control+A')
        await page.keyboard.press('Backspace')
        await page.keyboard.insert_text(title_text)
        await page.wait_for_timeout(1000)
        actual = await loc.inner_text(timeout=3000)
        await page.screenshot(path=str(outdir / "after_title.png"), full_page=True)
        data = {"title_expected": title_text, "title_actual": actual, "url": page.url}
        (outdir / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

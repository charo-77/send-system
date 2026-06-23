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
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS, fill_article_form
from playwright.async_api import async_playwright

ARTICLE_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\军事")

async def main() -> None:
    outdir = base / "debug" / "fill_military_once"
    outdir.mkdir(parents=True, exist_ok=True)
    files = list_docx(ARTICLE_DIR)
    article = extract_docx_article(files[0])
    cookies = load_cookie_file(Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513\ck.txt"))

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_fill_military_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(outdir / "before_fill.png"), full_page=True)
        (outdir / "01_before_fill.json").write_text(json.dumps({"url": page.url}, ensure_ascii=False, indent=2), encoding="utf-8")
        fill = await fill_article_form(page, article)
        (outdir / "02_fill_result.json").write_text(json.dumps(fill, ensure_ascii=False, indent=2), encoding="utf-8")
        await page.wait_for_timeout(2000)
        verify = await page.evaluate("""() => ({
            title: (document.querySelector('[data-testid=\"news-title-input\"] [contenteditable=\"true\"]')?.innerText || '').trim(),
            bodyPlaceholderSeen: (document.body?.innerText || '').includes('请输入正文'),
            publishSeen: (document.body?.innerText || '').includes('发布')
        })""")
        (outdir / "03_verify_partial.json").write_text(json.dumps(verify, ensure_ascii=False, indent=2), encoding="utf-8")
        for fr in page.frames:
            if fr.name == "ueditor_0" or "ueditor_0" in fr.url:
                try:
                    verify["body"] = (await fr.locator("body").inner_text(timeout=3000)).strip()[:500]
                except Exception as e:
                    verify["body_error"] = str(e)
        await page.screenshot(path=str(outdir / "after_fill.png"), full_page=True)
        result = {
            "article_path": str(article.path),
            "article_title": article.title,
            "fill": fill,
            "verify": verify,
            "url": page.url,
        }
        (outdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

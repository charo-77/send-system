from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import extract_docx_article, list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS, fill_article_form
from playwright.async_api import async_playwright

ARTICLE_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\国际")

async def main() -> None:
    outdir = base / "debug"
    outdir.mkdir(exist_ok=True)
    files = list_docx(ARTICLE_DIR)
    if not files:
        raise SystemExit(f"no docx under {ARTICLE_DIR}")
    article = extract_docx_article(files[0])
    cookies = load_cookie_file(base / "ck.txt")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / "edge_profile"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(outdir / "before_fill.png"), full_page=True)
        res = await fill_article_form(page, article)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(outdir / "after_fill.png"), full_page=True)
        data = await page.evaluate(
            """() => Array.from(document.querySelectorAll('button, [role=button], input[type=button], input[type=submit], .ant-btn, .arco-btn, [class*=btn], [class*=Btn]')).map((el, i) => ({
                i,
                tag: el.tagName,
                text: (el.innerText || el.value || el.textContent || '').trim(),
                cls: String(el.className || ''),
                id: el.id || '',
                aria: el.getAttribute('aria-label'),
                disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()
            })).slice(0,300)"""
        )
        (outdir / "buttons.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        body_text = await page.locator("body").inner_text(timeout=10000)
        (outdir / "body_text.txt").write_text(body_text[:20000], encoding="utf-8")
        print(json.dumps({"fill": res, "debug": str(outdir), "url": page.url}, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

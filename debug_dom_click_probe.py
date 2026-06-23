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
    outdir = base / "debug" / "dom_click_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    files = list_docx(ARTICLE_DIR)
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
        await page.wait_for_timeout(3000)
        fill = await fill_article_form(page, article)
        probe = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('button, [role=button], .op-btn-outter-content'));
            return els.map((el, i) => {
                const r = el.getBoundingClientRect();
                return {i, text: (el.innerText || el.value || el.textContent || '').trim(), tag: el.tagName, cls: String(el.className || ''), visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length), rect: {x:r.x,y:r.y,w:r.width,h:r.height}};
            }).filter(x => x.text === '发布');
        }""")
        await page.screenshot(path=str(outdir / "probe.png"), full_page=True)
        result = {"fill": fill, "publish_targets": probe, "url": page.url}
        (outdir / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

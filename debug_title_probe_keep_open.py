from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import extract_docx_article, list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

ARTICLE_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\国际")

async def main() -> None:
    outdir = base / "debug" / "title_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    files = list_docx(ARTICLE_DIR)
    article = extract_docx_article(files[0])
    cookies = load_cookie_file(base / "ck.txt")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(base / "edge_profile_title_probe"), channel="msedge", headless=False, viewport={"width": 1400, "height": 900}, args=["--disable-blink-features=AutomationControlled"])
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        data = await page.evaluate("""() => {
            const q = 'input, textarea, [contenteditable=true], [contenteditable="true"], [role=textbox]';
            return Array.from(document.querySelectorAll(q)).map((el, i) => {
                const r = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return {
                    i, tag: el.tagName, cls: String(el.className || ''), id: el.id || '',
                    placeholder: el.getAttribute('placeholder'), aria: el.getAttribute('aria-label'), role: el.getAttribute('role'),
                    text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 120),
                    contenteditable: el.getAttribute('contenteditable'), visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                    rect: {x:r.x,y:r.y,w:r.width,h:r.height}, fontSize: style.fontSize, fontWeight: style.fontWeight
                };
            }).filter(x => x.visible).slice(0, 100);
        }""")
        (outdir / "fields.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        await page.screenshot(path=str(outdir / "fields.png"), full_page=True)
        print(json.dumps({"title": article.title, "fields": data}, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

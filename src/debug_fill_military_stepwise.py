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
    outdir = base / "debug" / "fill_military_stepwise"
    outdir.mkdir(parents=True, exist_ok=True)
    files = list_docx(ARTICLE_DIR)
    article = extract_docx_article(files[0])
    title_text = (article.title or '').strip()[:64].rstrip()
    body_text = (article.body or '').strip()
    if title_text and body_text.startswith(title_text):
        deduped = body_text[len(title_text):].lstrip('\r\n ').strip()
        if deduped:
            body_text = deduped
    html = article.body_html or ''.join(f'<p>{line}</p>' for line in body_text.splitlines() if line.strip())
    cookies = load_cookie_file(Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513\ck.txt"))

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_fill_stepwise_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        await page.screenshot(path=str(outdir / "01_before.png"), full_page=True)

        sel = '[data-testid="news-title-input"] [contenteditable="true"][data-lexical-editor="true"]'
        loc = page.locator(sel).first
        await loc.wait_for(timeout=30000)
        await loc.evaluate("""el => { el.focus(); const range = document.createRange(); range.selectNodeContents(el); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); }""")
        await page.keyboard.press('Control+A')
        await page.keyboard.press('Backspace')
        await page.keyboard.insert_text(title_text)
        await page.wait_for_timeout(1000)
        actual_title = await loc.inner_text(timeout=3000)
        (outdir / '02_after_title.json').write_text(json.dumps({"title_expected": title_text, "title_actual": actual_title}, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(outdir / "02_after_title.png"), full_page=True)

        frame_el = await page.wait_for_selector('iframe#ueditor_0', timeout=30000)
        frame = await frame_el.content_frame()
        await frame.wait_for_load_state('domcontentloaded', timeout=30000)
        body = frame.locator('body').first
        await body.click(force=True)
        (outdir / '03_before_body.json').write_text(json.dumps({"clicked_body": True}, ensure_ascii=False, indent=2), encoding='utf-8')

        info = await body.evaluate(
            """(el, payload) => {
                el.innerHTML = payload.html;
                el.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, data: payload.text, inputType: 'insertText' }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return {
                    textPrefix: (el.innerText || '').slice(0, 200),
                    htmlPrefix: (el.innerHTML || '').slice(0, 500),
                    textLength: (el.innerText || '').length,
                    imgCount: el.querySelectorAll('img').length,
                };
            }""",
            {"html": html, "text": body_text},
        )
        (outdir / '04_after_body_write.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.wait_for_timeout(2000)
        count_text = await page.locator('#editWorldCount .count').inner_text(timeout=3000)
        (outdir / '05_after_count.json').write_text(json.dumps({"count_text": count_text}, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(outdir / "05_after_body.png"), full_page=True)
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

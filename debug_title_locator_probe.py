from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

async def main() -> None:
    outdir = base / "debug" / "title_locator_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(base / "ck.txt")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / "edge_profile_title_locator"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        data = await page.evaluate("""() => {
            function pack(el, i) {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return {
                    i,
                    tag: el.tagName,
                    cls: String(el.className || ''),
                    id: el.id || '',
                    name: el.getAttribute('name'),
                    type: el.getAttribute('type'),
                    placeholder: el.getAttribute('placeholder'),
                    aria: el.getAttribute('aria-label'),
                    role: el.getAttribute('role'),
                    title: el.getAttribute('title'),
                    text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 120),
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                    rect: {x:r.x,y:r.y,w:r.width,h:r.height},
                    fontWeight: s.fontWeight,
                    fontSize: s.fontSize,
                };
            }
            const selectors = [
                'input', 'textarea', '[contenteditable="true"]', '[role="textbox"]', '[class*=title]', '[class*=Title]', '[placeholder]'
            ];
            const arr = [];
            for (const sel of selectors) {
                Array.from(document.querySelectorAll(sel)).forEach((el, i) => arr.push(pack(el, i)));
            }
            const frames = Array.from(document.querySelectorAll('iframe')).map((f, i) => {
                const r = f.getBoundingClientRect();
                return {i, src: f.src || '', name: f.name || '', title: f.title || '', rect: {x:r.x,y:r.y,w:r.width,h:r.height}, visible: !!(f.offsetWidth || f.offsetHeight || f.getClientRects().length)};
            });
            return {fields: arr.filter(x => x.visible).slice(0, 200), frames};
        }""")
        (outdir / "locator.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        await page.screenshot(path=str(outdir / "locator.png"), full_page=True)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

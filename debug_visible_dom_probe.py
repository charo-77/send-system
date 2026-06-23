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
    outdir = base / "debug" / "visible_dom_probe"
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(base / "ck.txt")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(base / "edge_profile_visible_dom"), channel="msedge", headless=False, viewport={"width": 1400, "height": 900}, args=["--disable-blink-features=AutomationControlled"])
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        data = await page.evaluate("""() => {
            const out = [];
            if (!document.body) return {error:'no body', url: location.href, ready: document.readyState};
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let i = 0;
            while (walker.nextNode()) {
                const el = walker.currentNode;
                const r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0 || r.y < 0 || r.y > 900 || r.x < 0 || r.x > 1100) continue;
                const txt = (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g, ' ');
                const cls = String(el.className || '');
                const s = getComputedStyle(el);
                if (txt || cls.includes('editor') || cls.includes('Editor') || cls.includes('title') || cls.includes('Title')) {
                    out.push({
                        i: i++, tag: el.tagName, cls, id: el.id || '', txt: txt.slice(0, 160),
                        ce: el.getAttribute('contenteditable'), role: el.getAttribute('role'), ph: el.getAttribute('placeholder'),
                        rect: {x:r.x,y:r.y,w:r.width,h:r.height}, font: s.fontSize, weight: s.fontWeight,
                        childCount: el.children.length
                    });
                }
            }
            return {url: location.href, ready: document.readyState, bodyText: (document.body.innerText||'').slice(0,500), out: out.slice(0,500)};
        }""")
        (outdir / "visible_dom.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        await page.screenshot(path=str(outdir / "visible_dom.png"), full_page=True)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

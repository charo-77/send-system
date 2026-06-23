from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from cookies import load_cookie_file


async def main() -> int:
    repo_root = Path(r"D:\milu_publish_reverse_20260513")
    ck_path = repo_root / "runtime" / "account_manager" / "probe_cookie.txt"
    cookies = load_cookie_file(ck_path)
    out = repo_root / "runtime" / "account_manager"
    out.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=False)
        context = await browser.new_context(viewport={"width": 1440, "height": 960})
        await context.add_cookies(
            [
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain or ".baidu.com",
                    "path": c.path or "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
                for c in cookies
            ]
        )
        page = await context.new_page()
        await page.goto("https://baijiahao.baidu.com/builder/rc/home", wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(12000)
        data = {
            "url": page.url,
            "title": await page.title(),
            "content_len": len(await page.content()),
            "body_text_len": await page.evaluate("document.body ? document.body.innerText.length : -1"),
            "frame_count": len(page.frames),
            "frames": [{"name": f.name, "url": f.url} for f in page.frames],
        }
        (out / "probe_meta.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "probe.html").write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(out / "probe.png"), full_page=True)
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

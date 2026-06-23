from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from cookies import load_cookie_file


KEYWORDS = [
    "publish",
    "content",
    "article",
    "news",
    "video",
    "list",
    "quota",
    "draft",
    "tasksquare",
]


async def main() -> int:
    repo_root = Path(r"D:\milu_publish_reverse_20260513")
    ck_path = repo_root / "runtime" / "account_manager" / "probe_cookie.txt"
    cookies = load_cookie_file(ck_path)
    out = repo_root / "runtime" / "account_manager"
    out.mkdir(parents=True, exist_ok=True)
    records = []

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

        async def on_response(resp):
            url = resp.url
            lower = url.lower()
            if not any(key in lower for key in KEYWORDS):
                return
            try:
                text = await resp.text()
            except Exception:
                text = ""
            records.append({
                "url": url,
                "status": resp.status,
                "method": resp.request.method,
                "resource_type": resp.request.resource_type,
                "text": text[:15000],
            })

        page.on("response", on_response)
        for url in [
            "https://baijiahao.baidu.com/builder/rc/content",
            "https://baijiahao.baidu.com/builder/rc/content/all",
            "https://baijiahao.baidu.com/builder/rc/edit?type=news",
            "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
        ]:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_timeout(12000)
            except Exception:
                pass
        (out / "probe_publish_quota.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

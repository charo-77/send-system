from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from account_store import DEFAULT_ACCOUNT_STORE, load_account_records, now_iso
from browser_publish import inject_cookies
from cookies import load_cookie_file


async def open_account_session(
    cookie_text: str,
    profile_dir: Path,
    url: str,
    headless: bool = False,
    hold_seconds: int = 0,
) -> dict:
    profile_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = profile_dir / "account_ck.txt"
    cookie_file.write_text(cookie_text, encoding="utf-8")
    cookies = load_cookie_file(cookie_file)

    async with async_playwright() as p:
        edge_executable = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        launch_kwargs = {
            "headless": headless,
            "viewport": {"width": 1400, "height": 900},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if edge_executable.exists():
            launch_kwargs["executable_path"] = str(edge_executable)
        else:
            launch_kwargs["channel"] = "msedge"

        context = await p.chromium.launch_persistent_context(str(profile_dir), **launch_kwargs)
        injected = await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        title = await page.title()
        result = {
            "opened": True,
            "url": page.url,
            "title": title,
            "cookies_injected": injected,
            "profile_dir": str(profile_dir),
            "opened_at": now_iso(),
        }
        if hold_seconds > 0:
            await page.wait_for_timeout(hold_seconds * 1000)
            await context.close()
            result["auto_closed"] = True
        else:
            while True:
                await page.wait_for_timeout(3600000)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Open one account session in a real browser window using local CK")
    ap.add_argument("--worker", required=True)
    ap.add_argument("--store", default=str(DEFAULT_ACCOUNT_STORE))
    ap.add_argument("--profile-root", default=r"D:\milu_publish_reverse_20260513\runtime\account_manager\profiles")
    ap.add_argument("--url", default="https://baijiahao.baidu.com/builder/rc/home")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--hold-seconds", type=int, default=0)
    args = ap.parse_args()

    accounts = load_account_records(Path(args.store))
    target = None
    worker = str(args.worker or "").strip()
    for item in accounts:
        if item.worker_name == worker:
            target = item
            break
    if target is None:
        raise SystemExit(f"账号库中找不到 worker: {worker}")
    if not target.ck:
        raise SystemExit(f"账号缺少 CK: {worker}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = ''.join(ch if ch.isalnum() or ch in ('-', '_') else '_' for ch in worker) or 'worker'
    profile_dir = Path(args.profile_root) / f"{safe_name}_{stamp}"
    result = await open_account_session(
        cookie_text=target.ck,
        profile_dir=profile_dir,
        url=args.url,
        headless=args.headless,
        hold_seconds=args.hold_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

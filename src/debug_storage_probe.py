from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from cookies import load_cookie_file


STORAGE_JS = r"""
(() => {
  const dumpStorage = store => {
    const out = {};
    try {
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i);
        out[key] = store.getItem(key);
      }
    } catch (err) {}
    return out;
  };
  const entries = performance.getEntriesByType('resource').map(item => ({
    name: item.name,
    initiatorType: item.initiatorType,
  }));
  return {
    url: location.href,
    localStorage: dumpStorage(window.localStorage),
    sessionStorage: dumpStorage(window.sessionStorage),
    perfEntries: entries.filter(item => /(user|member|account|author|profile|income|quota|home|feed)/i.test(item.name)).slice(0, 200),
  };
})();
"""


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
        await page.wait_for_timeout(15000)
        payload = await page.evaluate(STORAGE_JS)
        (out / "probe_storage.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

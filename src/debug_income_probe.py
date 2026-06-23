from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from cookies import load_cookie_file


SCRIPT = r"""
(async () => {
  const candidates = [
    { url: '/author/eco/income4/homepageincome', options: {} },
    { url: `/author/eco/statistics/appStatisticV2?type=all&is_yesterday=true&start_day=${new Date(Date.now()-86400000).toISOString().slice(0,10).replace(/-/g,'')}&end_day=${new Date(Date.now()-86400000).toISOString().slice(0,10).replace(/-/g,'')}&stat=0`, options: {} },
  ];
  const out = [];
  for (const item of candidates) {
    try {
      const resp = await fetch(item.url, {
        credentials: 'include',
        headers: {
          'x-requested-with': 'XMLHttpRequest',
          'accept': 'application/json, text/plain, */*'
        },
        ...item.options,
      });
      out.push({ url: item.url, ok: resp.ok, status: resp.status, text: await resp.text() });
    } catch (err) {
      out.push({ url: item.url, ok: false, status: 0, error: String(err || '') });
    }
  }
  return out;
})()
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
        payload = await page.evaluate(SCRIPT)
        (out / "probe_income.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

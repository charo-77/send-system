from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from cookies import load_cookie_file


RUNTIME_JS = r"""
(() => {
  const out = {};
  const keys = Object.keys(window).filter(k => /(user|member|author|account|profile|name|nick)/i.test(k));
  out.windowKeys = keys.slice(0, 200);
  out.matches = [];
  for (const key of keys.slice(0, 80)) {
    try {
      const value = window[key];
      if (value == null) continue;
      const text = JSON.stringify(value);
      if (text && text.length < 4000) {
        out.matches.push({ key, value });
      }
    } catch (err) {
    }
  }
  const scriptTexts = Array.from(document.scripts).map((s, i) => ({ index: i, text: (s.textContent || '').slice(0, 60000) }));
  const patterns = [
    /(?:name|nickname|displayName|accountName|userName)["']?\s*[:=]\s*["']([^"'\\]{2,40})["']/gi,
    /(?:用户名|账号名|昵称)[:：]\s*([^\n\r"']{2,40})/gi,
  ];
  out.scriptHits = [];
  for (const script of scriptTexts) {
    for (const regex of patterns) {
      let match;
      while ((match = regex.exec(script.text)) !== null) {
        out.scriptHits.push({ scriptIndex: script.index, hit: match[1] });
      }
    }
  }
  return out;
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
        payload = await page.evaluate(RUNTIME_JS)
        (out / "probe_runtime.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

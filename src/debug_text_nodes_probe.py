from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from cookies import load_cookie_file


TEXT_JS = r"""
(() => {
  const compact = text => (text || '').replace(/\s+/g, ' ').trim();
  const nodes = Array.from(document.querySelectorAll('div, span, a, p, strong, em, li, td, h1, h2, h3, h4'));
  const rows = [];
  for (const node of nodes) {
    const text = compact(node.innerText || node.textContent || '');
    if (!text) continue;
    if (text.length > 30) continue;
    rows.push({
      text,
      tag: node.tagName,
      cls: node.className || '',
      id: node.id || '',
    });
  }
  return rows.slice(0, 500);
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
        await page.wait_for_timeout(12000)
        rows = await page.evaluate(TEXT_JS)
        (out / "probe_text_nodes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

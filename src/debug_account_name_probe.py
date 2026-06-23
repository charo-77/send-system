from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from account_store import DEFAULT_ACCOUNT_STORE, load_account_records
from playwright.async_api import async_playwright
from cookies import load_cookie_file


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "https://baijiahao.baidu.com/builder/rc/home"


PROBE_JS = r"""
(() => {
  const compact = text => (text || '').replace(/\s+/g, ' ').trim();
  const selectors = [
    '[class*="name"]',
    '[class*="user"] [class*="name"]',
    '[class*="avatar"] + *',
    '[class*="nickname"]',
    '[class*="account"] [class*="title"]',
    '[class*="profile"] [class*="title"]',
    'a[href*="profile"]',
    'header a',
    'header span',
    '[data-testid*="name"]',
    '[data-testid*="user"]'
  ];
  const selectorHits = [];
  for (const selector of selectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    selectorHits.push({
      selector,
      values: nodes.slice(0, 20).map(node => compact(node.innerText || node.textContent || '')).filter(Boolean),
    });
  }

  const scripts = Array.from(document.scripts).map((s, index) => ({
    index,
    text: (s.textContent || '').slice(0, 20000),
  }));
  const regexes = [
    /(?:name|nickname|displayName|accountName|userName)["']?\s*[:=]\s*["']([^"'\\]{2,40})["']/gi,
    /(?:用户名|账号名|昵称)[:：]\s*([^\n\r"']{2,40})/gi
  ];
  const scriptMatches = [];
  for (const script of scripts) {
    for (const regex of regexes) {
      let match;
      while ((match = regex.exec(script.text)) !== null) {
        scriptMatches.push({ scriptIndex: script.index, value: compact(match[1]) });
      }
    }
  }

  return {
    title: compact(document.title || ''),
    url: location.href,
    bodySample: compact(document.body ? document.body.innerText : '').slice(0, 5000),
    selectorHits,
    scriptMatches,
  };
})();
"""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", required=True)
    ap.add_argument("--store", default=str(DEFAULT_ACCOUNT_STORE))
    ap.add_argument("--out", default=str(REPO_ROOT / "runtime" / "account_manager" / "name_probe.json"))
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()

    accounts = load_account_records(Path(args.store))
    target = next((item for item in accounts if item.worker_name == args.worker), None)
    if target is None:
        raise SystemExit(f"worker not found: {args.worker}")

    tmp_cookie = REPO_ROOT / "runtime" / "account_manager" / "probe_cookie.txt"
    tmp_cookie.write_text(target.ck, encoding="utf-8")
    cookies = load_cookie_file(tmp_cookie)

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=False)
        context = await browser.new_context(viewport={"width": 1440, "height": 960})
        converted = []
        for item in cookies:
            converted.append(
                {
                    "name": item.name,
                    "value": item.value,
                    "domain": item.domain or ".baidu.com",
                    "path": item.path or "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            )
        await context.add_cookies(converted)
        page = await context.new_page()
        await page.goto(args.url, wait_until="networkidle", timeout=90000)
        await page.wait_for_timeout(5000)
        payload = await page.evaluate(PROBE_JS)
        payload["worker_name"] = target.worker_name
        payload["account_name"] = target.account_name
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(out_path))
        await browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

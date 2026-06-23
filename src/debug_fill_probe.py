from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from articles import extract_docx_article
from browser_publish import fill_article_form, inject_cookies
from cookies import load_cookie_file


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile-dir', required=True)
    ap.add_argument('--cookie-file', required=True)
    ap.add_argument('--docx', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    article = extract_docx_article(Path(args.docx))
    cookies = load_cookie_file(Path(args.cookie_file))

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(Path(args.profile_dir)),
            executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        if cookies:
            await inject_cookies(context, cookies)

        await page.goto('https://baijiahao.baidu.com/builder/rc/edit?type=news', wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(8000)

        before = {
            'url': page.url,
            'title': await page.title(),
            'body': (await page.locator('body').inner_text(timeout=3000))[:3000],
        }
        (out_dir / '01_before_fill.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')

        result = await fill_article_form(page, article)
        (out_dir / '02_fill_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

        after = {
            'url': page.url,
            'title': await page.title(),
            'body': (await page.locator('body').inner_text(timeout=3000))[:5000],
        }
        (out_dir / '03_after_fill.json').write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding='utf-8')

        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

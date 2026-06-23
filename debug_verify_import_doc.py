from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies, upload_word_document
from playwright.async_api import async_playwright

CK = base / "ck.txt"
ARTICLES = Path(r"C:\Users\Administrator\Desktop\mingming\国际")


async def main():
    outdir = base / 'debug' / 'verify_import_doc'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_verify_import_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto('https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1', wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(8000)

        result = await upload_word_document(page, docx)
        await page.screenshot(path=str(outdir / 'after_upload_attempt.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await page.wait_for_timeout(3000)
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

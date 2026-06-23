from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(r'D:\milu_publish_reverse_20260513')
sys.path.insert(0, str(BASE / 'src'))

from articles import extract_docx_article, extract_docx_images, list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies, fill_article_form, upload_word_document, choose_cover_from_imported_images, select_activities

ARTICLES_DIR = Path(r'C:\Users\Administrator\Desktop\mingming\鍥炬枃')
CK = BASE / 'ck.txt'
PROFILE = BASE / 'edge_profile_news_hold_20260525'
DEBUG_DIR = BASE / 'debug' / 'news_hold_20260525_2325'
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news'

async def main():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    files = list_docx(ARTICLES_DIR)
    if not files:
        raise SystemExit('no docx files found')
    docx_path = files[0]
    article = extract_docx_article(docx_path)
    docx_images = extract_docx_images(docx_path, DEBUG_DIR / 'covers')
    cookies = load_cookie_file(CK)

    p = await async_playwright().start()
    context = await p.chromium.launch_persistent_context(
        str(PROFILE),
        channel='msedge',
        headless=False,
        viewport={'width': 1440, 'height': 960},
        args=['--disable-blink-features=AutomationControlled'],
    )
    injected = await inject_cookies(context, cookies)
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(6000)

    fill_result = await fill_article_form(page, article)
    import_result = await upload_word_document(page, docx_path, article)
    await page.wait_for_timeout(4000)
    cover_result = await choose_cover_from_imported_images(page, len(docx_images)) if docx_images else {'attempted': False}
    await page.wait_for_timeout(2000)
    activity_result = await select_activities(page, ['AI鏂囧彶鐧惧伐涓浗'])
    await page.wait_for_timeout(2000)

    state = await page.evaluate("""() => ({url: location.href, title: document.title, body: (document.body.innerText || '').slice(0, 12000)})""")
    out = {
        'docx_path': str(docx_path),
        'cookies_injected': injected,
        'fill_result': fill_result,
        'import_result': import_result,
        'cover_result': cover_result,
        'activity_result': activity_result,
        'state': state,
    }
    (DEBUG_DIR / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(DEBUG_DIR / 'after.png'), full_page=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print('HOLDING_NEWS_BROWSER_OPEN')
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())


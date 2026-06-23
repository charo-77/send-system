from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from playwright.async_api import async_playwright
from articles import extract_docx_article, list_docx
from browser_publish import inject_cookies, fill_article_form, dismiss_tours_and_overlays, choose_cover_from_imported_images
from cookies import load_cookie_file

COOKIE_FILE = base / 'ck.txt'
ARTICLES_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\国际")
OUTDIR = base / 'debug' / 'probe_ai_cover_empty_article'
PROFILE = base / 'edge_profile_probe_ai_cover_empty'
EDIT_URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news'

JS_SCAN = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
  const all = Array.from(document.querySelectorAll('button,[role=button],div,span,a,label'));
  const hits = all.map((el, i) => {
    const t = textOf(el);
    const cls = String(el.className || '');
    const aria = el.getAttribute?.('aria-label') || '';
    const score = /封面|图片|图像|生成|智能|AI|配图/.test(t + ' ' + aria + ' ' + cls) ? 1 : 0;
    return {i, t, cls, aria, rect: rectOf(el), score};
  }).filter(x => x.score && x.rect.w > 20 && x.rect.h > 16).slice(0, 300);

  const reactCandidates = Array.from(document.querySelectorAll('*')).map((el, i) => {
    const keys = Object.keys(el).filter(k => k.startsWith('__reactProps$'));
    if (!keys.length) return null;
    const cls = String(el.className || '');
    const txt = textOf(el);
    if (!/cover|Cover|封面|AI|智能|图片|图像|生成/.test(cls + ' ' + txt)) return null;
    return {i, tag: el.tagName, cls, txt: txt.slice(0, 200), reactKeys: keys.slice(0, 3)};
  }).filter(Boolean).slice(0, 80);

  return {
    url: location.href,
    title: document.title,
    bodyText: (document.body.innerText || '').slice(0, 5000),
    hits,
    reactCandidates,
  };
}'''

async def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    docx_files = list_docx(ARTICLES_DIR)
    if not docx_files:
        raise RuntimeError('no docx files found')
    article = extract_docx_article(docx_files[0])

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        cookies = load_cookie_file(COOKIE_FILE)
        await inject_cookies(context, cookies)
        await page.goto(EDIT_URL, wait_until='domcontentloaded')
        await page.wait_for_load_state('networkidle')
        await dismiss_tours_and_overlays(page)
        empty_article = article.__class__(path=article.path, title=article.title, body='', body_html='')
        await fill_article_form(page, empty_article)
        await page.wait_for_timeout(2500)
        open_result = await choose_cover_from_imported_images(page, 0)
        await page.wait_for_timeout(1500)
        state = await page.evaluate(JS_SCAN)
        await page.screenshot(path=str(OUTDIR / 'empty_article_cover_probe.png'), full_page=True)
        result = {
            'article': str(article.path),
            'open_cover_selector': open_result,
            'state': state,
        }
        (OUTDIR / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

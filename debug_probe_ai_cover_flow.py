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
OUTDIR = base / 'debug' / 'probe_ai_cover_flow'
PROFILE = base / 'edge_profile_probe_ai_cover_flow'
EDIT_URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news'

JS_CLICK_AI_TAB = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const nodes = Array.from(document.querySelectorAll('.cheetah-tabs-tab, [role=tab], button, div, span, a'));
  const rows = nodes.map((el, i) => {
    const t = textOf(el);
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === 'AI封图') score += 500;
    if (/AI封图/.test(t)) score += 300;
    return {el, i, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score};
  }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 16).sort((a,b) => b.score - a.score);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.slice(0,20).map(x => ({t:x.t, cls:x.cls, rect:x.rect, score:x.score}))};
  const r = picked.rect;
  try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, rect:picked.rect}};
}'''

JS_SCAN = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
  const hits = Array.from(document.querySelectorAll('button,[role=button],div,span,a,label,input,textarea')).map((el, i) => {
    const t = textOf(el);
    const cls = String(el.className || '');
    const aria = el.getAttribute?.('aria-label') || '';
    const ph = el.getAttribute?.('placeholder') || '';
    const score = /AI封图|生成|智能|封面|图片|图像|提示词|关键词|立即生成|重新生成|确认|确定|应用/.test([t, cls, aria, ph].join(' ')) ? 1 : 0;
    return {i, tag: el.tagName, t, cls, aria, ph, rect: rectOf(el), score};
  }).filter(x => x.score && x.rect.w > 10 && x.rect.h > 10).slice(0, 400);
  return {
    bodyText: (document.body.innerText || '').slice(0, 8000),
    hits,
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
        click_ai_tab = await page.evaluate(JS_CLICK_AI_TAB)
        await page.wait_for_timeout(2500)
        state = await page.evaluate(JS_SCAN)
        await page.screenshot(path=str(OUTDIR / 'ai_cover_flow.png'), full_page=True)
        result = {
            'article': str(article.path),
            'open_cover_selector': open_result,
            'click_ai_tab': click_ai_tab,
            'state': state,
        }
        (OUTDIR / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

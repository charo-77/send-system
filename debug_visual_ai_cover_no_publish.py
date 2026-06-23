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
OUTDIR = base / 'debug' / 'visual_ai_cover_no_publish'
PROFILE = base / 'edge_profile_visual_ai_cover_no_publish'
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
  try { picked.el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
  try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, rect:picked.rect}};
}'''

JS_CLICK_GENERATE = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const nodes = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = nodes.map((el, i) => {
    const t = textOf(el);
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === '根据全文智能生成封面') score += 600;
    if (/根据全文智能生成封面/.test(t)) score += 450;
    if (/一键智能生图/.test(t)) score += 300;
    if (/生成AI图片/.test(t)) score += 220;
    return {el, i, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score};
  }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 16).sort((a,b) => b.score - a.score);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.slice(0,30).map(x => ({t:x.t, cls:x.cls, rect:x.rect, score:x.score}))};
  const r = picked.rect;
  try { picked.el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
  try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, rect:picked.rect}};
}'''

JS_SCAN = r'''() => {
  return {
    url: location.href,
    title: document.title,
    bodyText: (document.body.innerText || '').slice(0, 8000),
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
        await page.wait_for_timeout(2000)
        click_generate = await page.evaluate(JS_CLICK_GENERATE)
        await page.wait_for_timeout(1000)
        state1 = await page.evaluate(JS_SCAN)
        await page.screenshot(path=str(OUTDIR / 'after_click_generate.png'), full_page=True)
        result = {
            'article': str(article.path),
            'open_cover_selector': open_result,
            'click_ai_tab': click_ai_tab,
            'click_generate': click_generate,
            'state_after_generate_click': state1,
        }
        (OUTDIR / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('VISUAL_BROWSER_READY_KEEP_OPEN')
        await page.wait_for_timeout(600000)

if __name__ == '__main__':
    asyncio.run(main())

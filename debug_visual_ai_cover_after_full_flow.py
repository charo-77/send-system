from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from playwright.async_api import async_playwright
from articles import extract_docx_article, list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies, fill_article_form, dismiss_tours_and_overlays, upload_word_document, wait_import_confirm_and_click, _collect_page_state, choose_cover_from_imported_images

COOKIE_FILE = base / 'ck.txt'
ARTICLES_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\国际")
OUTDIR = base / 'debug' / 'visual_ai_cover_after_full_flow'
PROFILE = base / 'edge_profile_visual_ai_cover_after_full_flow'
EDIT_URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news'

JS_CLICK_AI_TAB = r'''() => {
  const el = document.getElementById('rc-tabs-0-tab-ai') || Array.from(document.querySelectorAll('.cheetah-tabs-tab-btn,.cheetah-tabs-tab,[role=tab]')).find(x => ((x.innerText||x.textContent||'').trim() === 'AI封图'));
  if (!el) return {ok:false, reason:'ai-tab-not-found'};
  const r = el.getBoundingClientRect();
  try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
  try { if (typeof el.click === 'function') el.click(); } catch (_) {}
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {ok:true, text:(el.innerText||el.textContent||'').trim(), id:el.id || '', cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

JS_CLICK_FULLTEXT_AI = r'''() => {
  const el = document.querySelector('.FeEditorApp-_6853aa778d53acdc-theme') || Array.from(document.querySelectorAll('span,div,button,a')).find(x => ((x.innerText||x.textContent||'').trim() === '根据全文智能生成封面'));
  if (!el) {
    const rows = Array.from(document.querySelectorAll('span,div,button,a')).map(x => ({
      t: ((x.innerText||x.textContent||'').trim()),
      cls: String(x.className||''),
    })).filter(x => /根据全文智能生成封面|AI封图|一键智能生图/.test(x.t + ' ' + x.cls)).slice(0, 30);
    return {ok:false, reason:'fulltext-ai-link-not-found', rows};
  }
  const r = el.getBoundingClientRect();
  try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
  try { if (typeof el.click === 'function') el.click(); } catch (_) {}
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {ok:true, text:(el.innerText||el.textContent||'').trim(), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

JS_SCAN = r'''() => {
  const bodyText = (document.body.innerText || '').slice(0, 12000);
  const previewImgs = Array.from(document.querySelectorAll('.FeEditorApp-eb32f45bdacfe09a-container img, .FeEditorApp-_6853aa778d53acdc-right img, img'))
    .map(img => ({src: img.src, w: img.naturalWidth || img.width || 0, h: img.naturalHeight || img.height || 0}))
    .filter(x => !!x.src)
    .slice(0, 10);
  const confirmBtn = Array.from(document.querySelectorAll('button')).find(el => /^确定(\s*\(\d+\))?$/.test((el.innerText||el.textContent||'').trim()) && String(el.className||'').includes('FeEditorApp-_6853aa778d53acdc-confirm')) || null;
  return {
    url: location.href,
    title: document.title,
    bodyText,
    generating: /正在生成中|请稍后再试/.test(bodyText),
    hasRetry: /重新生成/.test(bodyText),
    confirmEnabled: !!(confirmBtn && !confirmBtn.disabled),
    previewImgs,
  };
}'''

async def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    docx_path = Path(r"C:\Users\Administrator\Desktop\mingming\国际\A发布失败\普京访华在即，俄乌战争都得让路.docx")
    if not docx_path.exists():
        raise RuntimeError(f'no such docx: {docx_path}')
    article = extract_docx_article(docx_path)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.bring_to_front()
        cookies = load_cookie_file(COOKIE_FILE)
        await inject_cookies(context, cookies)
        await page.goto(EDIT_URL, wait_until='domcontentloaded')
        await page.wait_for_load_state('networkidle')
        dismiss_result = await dismiss_tours_and_overlays(page)
        fill_result = await fill_article_form(page, article)
        await page.wait_for_timeout(1200)
        upload_result = await upload_word_document(page, docx_path)
        confirm_result = {'attempted': False, 'clicked': False, 'steps': []}
        if upload_result.get('uploaded'):
            confirm_result = await wait_import_confirm_and_click(page)
        await page.wait_for_timeout(1500)
        cover_open_result = await choose_cover_from_imported_images(page, 0)
        await page.wait_for_timeout(1200)
        click_ai_tab = await page.evaluate(JS_CLICK_AI_TAB)
        await page.wait_for_timeout(1800)
        click_fulltext_ai = await page.evaluate(JS_CLICK_FULLTEXT_AI)

        generation_checks = []
        state = None
        confirm_after_generation = None
        for i in range(1, 7):
            await page.wait_for_timeout(10000)
            state = await page.evaluate(JS_SCAN)
            generation_checks.append({"round": i, "state": state})
            if state.get('confirmEnabled'):
                confirm_after_generation = await page.evaluate(r'''() => {
                  const el = Array.from(document.querySelectorAll('button')).find(x => /^确定(\s*\(\d+\))?$/.test((x.innerText||x.textContent||'').trim()) && String(x.className||'').includes('FeEditorApp-_6853aa778d53acdc-confirm'));
                  if (!el) return {ok:false, reason:'confirm-not-found'};
                  const r = el.getBoundingClientRect();
                  try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                    el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
                  }
                  return {ok:true, text:(el.innerText||el.textContent||'').trim(), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                }''')
                break

        page_state = await _collect_page_state(page)
        state = await page.evaluate(JS_SCAN)
        await page.screenshot(path=str(OUTDIR / 'after_click_fulltext_ai.png'), full_page=True)
        result = {
            'dismiss': dismiss_result,
            'fill': fill_result,
            'upload': upload_result,
            'import_confirm': confirm_result,
            'cover_open': cover_open_result,
            'click_ai_tab': click_ai_tab,
            'click_fulltext_ai': click_fulltext_ai,
            'generation_checks': generation_checks,
            'confirm_after_generation': confirm_after_generation,
            'page_state': page_state,
            'state': state,
        }
        (OUTDIR / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('VISUAL_BROWSER_READY_KEEP_OPEN')
        await page.wait_for_timeout(600000)

if __name__ == '__main__':
    asyncio.run(main())

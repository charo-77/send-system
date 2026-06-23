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
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / 'ck.txt'
ARTICLES = Path(r"C:\Users\Administrator\Desktop\mingming\国际")
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1'

DISMISS = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span'));
  for (const el of els) {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    if (!(r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0)) continue;
    if (t === '我知道了' || t === '下一步' || String(el.className || '').includes('cheetah-tour-close')) {
      if (typeof el.click === 'function') el.click();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
    }
  }
  return true;
}'''

OPEN_INSERT = r'''() => {
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  if (!entry) return false;
  const r = entry.getBoundingClientRect();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  }
  try { entry.click(); } catch (_) {}
  return true;
}'''

CLICK_IMPORT = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const picked = items.find(el => el.querySelector('.l-icon-BjhBasicDaoruwendang')) || items.find(el => /导入文档/.test(textOf(el))) || null;
  if (!picked) return false;
  const r = picked.getBoundingClientRect();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  }
  try { picked.click(); } catch (_) {}
  return true;
}'''

SWITCH_THREE = r'''() => {
  const input = document.querySelector('input.cheetah-radio-input[name="cover"][value="three"]');
  const label = input ? input.closest('label') : null;
  const target = label || input;
  if (!target) return {ok:false};
  const r = target.getBoundingClientRect();
  if (input) {
    input.checked = true;
    input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  }
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  try { target.click(); } catch (_) {}
  return Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked}));
}'''

OPEN_VIA_REACT = r'''() => {
  const item = document.querySelector('.FeEditorApp-_93c3fe2a3121c388-item');
  if (!item) return {ok:false, error:'no item'};
  const key = Object.keys(item).find(k => k.startsWith('__reactProps$'));
  const props = key ? item[key] : null;
  const child = props?.children?.[0];
  const open = child?.props?.open;
  if (typeof open !== 'function') return {ok:false, error:'no open fn', key, childProps: child?.props ? Object.keys(child.props) : null};
  try {
    const ret = open();
    return {ok:true, key, childPropKeys: Object.keys(child.props || {}), retType: typeof ret};
  } catch (e) {
    return {ok:false, error:String(e), key};
  }
}'''

TRY_SELECT = r'''() => {
  const texts = Array.from(document.querySelectorAll('button,[role=button],div,span,label,a')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    return {t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.t && x.rect.w > 10 && x.rect.h > 10);

  const checks = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => {
    const wrap = el.closest('label,div,span,li') || el;
    const r = wrap.getBoundingClientRect();
    return {i, checked:!!el.checked, disabled:!!el.disabled, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(wrap.className||''), text:(wrap.innerText||wrap.textContent||'').trim().slice(0,80), wrap};
  }).filter(x => x.rect.w > 5 && x.rect.h > 5 && !x.disabled);

  const checkedBefore = checks.filter(x => x.checked).map(x => x.i);
  const need = Math.max(0, 3 - checkedBefore.length);
  const candidates = checks.filter(x => !x.checked).sort((a,b) => a.rect.y - b.rect.y || a.rect.x - b.rect.x);
  const clicked = [];
  for (const item of candidates.slice(0, need)) {
    const r = item.rect;
    try { if (typeof item.wrap.click === 'function') item.wrap.click(); } catch (_) {}
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      item.wrap.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
    }
    clicked.push({i:item.i, text:item.text, cls:item.cls, rect:item.rect});
  }

  const checkedAfter = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked:!!el.checked, disabled:!!el.disabled}));

  const confirmEls = texts.filter(x => /^确定(\s*\(\d+\))?$/.test(x.t) || x.t === '取消' || x.t === '确认');
  return {texts: texts.filter(x => /确定|取消|确认|封面|图片|上传|本地|图库/.test(x.t)).slice(0,150), checkedBefore, clicked, checkedAfter, confirmEls};
}'''

CLICK_CONFIRM = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    let score = 0;
    if (/^确定(\s*\(\d+\))?$/.test(t)) score += 400;
    if (t === '确认') score += 250;
    if (t === '完成') score += 220;
    if (cls.includes('primary')) score += 60;
    return {el, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score};
  }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 20).sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.slice(0,20).map(x => ({t:x.t, cls:x.cls, rect:x.rect, score:x.score}))};
  const r = picked.rect;
  try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, rect:picked.rect, score:picked.score}, rows: rows.slice(0,10).map(x => ({t:x.t, cls:x.cls, rect:x.rect, score:x.score}))};
}'''

SNAP = r'''() => ({
  bodySnippet: (document.body.innerText || '').slice(0, 8000),
  radioState: Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked})),
  checks: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked:!!el.checked, disabled:!!el.disabled})).slice(0,50),
  dialogs: Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="modal"], [class*="drawer"], [class*="popup"], [class*="popover"]')).map((el, i) => { const r = el.getBoundingClientRect(); return {i, cls:String(el.className||'').slice(0,160), txt:(el.innerText||'').slice(0,400), rect:{x:r.x,y:r.y,w:r.width,h:r.height}}; }).filter(x => x.rect.w > 40 && x.rect.h > 20).slice(0,50)
})'''

async def main():
    outdir = base / 'debug' / 'cover_open_via_react'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(base / f'edge_profile_cover_open_via_react_{int(time.time())}'),
        channel='msedge',
        headless=False,
        viewport={'width': 1400, 'height': 900},
        args=['--disable-blink-features=AutomationControlled'],
    )
    await inject_cookies(context, cookies)
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_function("() => !!document.querySelector('#ueditor_0') && !!document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry, #edui41_state')", timeout=120000)
    await page.wait_for_timeout(7000)
    await page.evaluate(DISMISS)
    await page.wait_for_timeout(1200)
    await page.evaluate(OPEN_INSERT)
    await page.wait_for_timeout(800)
    for _ in range(25):
        ok = await page.evaluate(CLICK_IMPORT)
        if ok:
            break
        await page.wait_for_timeout(200)
    locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
    await locator.set_input_files(str(docx))
    await page.wait_for_timeout(7000)
    switch_result = await page.evaluate(SWITCH_THREE)
    await page.wait_for_timeout(1200)
    open_result = await page.evaluate(OPEN_VIA_REACT)
    await page.wait_for_timeout(2500)
    select_result = await page.evaluate(TRY_SELECT)
    await page.wait_for_timeout(1200)
    confirm_result = await page.evaluate(CLICK_CONFIRM)
    await page.wait_for_timeout(3000)
    snap = await page.evaluate(SNAP)
    result = {
        'switch_result': switch_result,
        'open_result': open_result,
        'select_result': select_result,
        'confirm_result': confirm_result,
        'snap': snap,
    }
    (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / 'after_react_cover.png'), full_page=True)
    print(json.dumps({'status':'kept_alive','result_path': str(outdir / 'result.json'), 'open_result': open_result, 'confirm_result': confirm_result}, ensure_ascii=False))
    while True:
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

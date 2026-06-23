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
  const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  return true;
}'''

CLICK_IMPORT = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const picked = items.find(el => el.querySelector('.l-icon-BjhBasicDaoruwendang')) || items.find(el => /导入文档/.test(textOf(el))) || null;
  if (!picked) return false;
  const r = picked.getBoundingClientRect();
  const fire = type => picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
  return true;
}'''

SWITCH_THREE = r'''() => {
  const input = document.querySelector('input.cheetah-radio-input[name="cover"][value="three"]');
  const label = input ? input.closest('label') : null;
  const target = label || input;
  if (!target) return {ok:false, error:'no three radio'};
  const before = Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked}));
  const r = target.getBoundingClientRect();
  try { target.scrollIntoView({block:'center'}); } catch (_) {}
  if (input) {
    input.checked = true;
    input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  }
  if (typeof target.click === 'function') target.click();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  const after = Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked}));
  return {ok:true, before, after, cls:String(target.className||''), txt:(target.innerText||target.textContent||'').trim()};
}'''

OPEN_COVER_EXACT = r'''() => {
  const root = document.querySelector('#bjhNewsCover');
  if (!root) return {ok:false, error:'no #bjhNewsCover'};
  const cards = Array.from(root.querySelectorAll('.FeEditorApp-_93c3fe2a3121c388-item, .FeEditorApp-_73a3a52aab7e3a36-default, .FeEditorApp-_73a3a52aab7e3a36-content'));
  const visible = cards.filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 50 && r.height > 50;
  });
  const target = visible[0];
  if (!target) return {ok:false, error:'no visible cover card', cardCount:cards.length};
  const r = target.getBoundingClientRect();
  try { target.scrollIntoView({block:'center'}); } catch (_) {}
  if (typeof target.click === 'function') target.click();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {ok:true, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(target.className||''), txt:(target.innerText||target.textContent||'').trim(), cardCount:visible.length};
}'''

SNAP = r'''() => {
  const visibleTexts = Array.from(document.querySelectorAll('button,[role=button],div,span,a,label')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    const cls = String(el.className || '');
    return {t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.t && x.rect.w > 10 && x.rect.h > 10 && /单图|三图|选择封面|确定|取消|确认|图片|封面|图库|上传/.test(x.t)).slice(0,300);

  return {
    radioState: Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked})),
    visibleTexts,
    checkboxStates: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked:!!el.checked, disabled:!!el.disabled})).slice(0,30),
    bodySnippet: (document.body.innerText || '').slice(0, 5000),
  };
}'''

async def main():
    outdir = base / 'debug' / 'cover_switch_three_then_open'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(base / f'edge_profile_cover_switch_three_{int(time.time())}'),
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
    await page.wait_for_timeout(1500)
    open_result = await page.evaluate(OPEN_COVER_EXACT)
    await page.wait_for_timeout(3000)
    snap = await page.evaluate(SNAP)
    result = {'switch_result': switch_result, 'open_result': open_result, 'snap': snap}
    (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / 'after_switch_open.png'), full_page=True)
    print(json.dumps({'status':'kept_alive','result_path': str(outdir / 'result.json'), 'switch_result': switch_result, 'open_result': open_result}, ensure_ascii=False))
    while True:
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

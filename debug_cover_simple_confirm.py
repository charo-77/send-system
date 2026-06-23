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

OPEN_COVER = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const aria = el.getAttribute?.('aria-label') || '';
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === '选择封面') score += 320;
    if (t === '更换') score += 220;
    if (/更换封面/.test(aria)) score += 260;
    return {el, score, t, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.score > 0 && x.rect.w > 10 && x.rect.h > 10).sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false, rows};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, rect:picked.rect}};
}'''

SELECT_THREE = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a,input[type=radio]'));
  const rows = [];
  for (const el of els) {
    const wrap = el.closest('label,div,span,button,a') || el;
    const t = (wrap.innerText || wrap.textContent || '').trim();
    const r = wrap.getBoundingClientRect();
    let score = 0;
    if (t === '三图') score += 300;
    if (t.includes('三图')) score += 150;
    if (el.tagName === 'INPUT' && el.getAttribute('type') === 'radio' && el.getAttribute('value') === 'three') score += 250;
    if (score > 0 && r.width > 10 && r.height > 10) rows.push({el: wrap, score, t, rect:{x:r.x,y:r.y,w:r.width,h:r.height}});
  }
  rows.sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, rect:picked.rect}};
}'''

CLICK_THREE_BOXES = r'''() => {
  const boxes = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => {
    const wrap = el.closest('label,div,span,li') || el;
    const r = el.getBoundingClientRect();
    const wr = wrap.getBoundingClientRect();
    return {i, el, wrap, checked: !!el.checked, disabled: !!el.disabled, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, wrapRect:{x:wr.x,y:wr.y,w:wr.width,h:wr.height}};
  }).filter(x => !x.disabled);

  const chosen = [];
  for (const item of boxes.slice(0, 3)) {
    const r = item.rect.w > 0 ? item.rect : item.wrapRect;
    const target = item.el;
    if (!item.checked) {
      if (typeof target.click === 'function') target.click();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        target.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
      }
    }
    chosen.push({i:item.i, before:item.checked, rect:r});
  }
  const after = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked: !!el.checked, disabled: !!el.disabled}));
  return {ok:true, chosen, after};
}'''

CONFIRM_COVER = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    let score = 0;
    if (/^确定(\s*\(\d+\))?$/.test(t)) score += 400;
    if (t === '确认') score += 360;
    if (cls.includes('primary')) score += 120;
    if (r.y > 2400) score += 200;
    return {el, t, cls, score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 20).sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.slice(0,30)};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, rect:picked.rect}, rows: rows.slice(0,10)};
}'''

READ = r'''() => ({
  bodyText: (document.body.innerText || '').slice(0, 8000),
  checkboxStates: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked: !!el.checked, disabled: !!el.disabled})).slice(0, 50),
  visibleButtons: Array.from(document.querySelectorAll('button,[role=button],div,span,a')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return {t, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.t && x.rect.w > 20 && x.rect.h > 20 && x.rect.y > 2300).slice(0, 100)
})'''

async def main():
    outdir = base / 'debug' / 'cover_simple_confirm'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(base / f'edge_profile_cover_simple_{int(time.time())}'),
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

    result = {}
    await page.evaluate(DISMISS)
    await page.wait_for_timeout(1200)
    await page.evaluate(OPEN_INSERT)
    await page.wait_for_timeout(800)
    for _ in range(25):
        ok = await page.evaluate(CLICK_IMPORT)
        if ok:
            result['click_import'] = True
            break
        await page.wait_for_timeout(200)
    locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
    await locator.set_input_files(str(docx))
    await page.wait_for_timeout(5000)

    result['open_cover'] = await page.evaluate(OPEN_COVER)
    await page.wait_for_timeout(1500)
    result['select_three'] = await page.evaluate(SELECT_THREE)
    await page.wait_for_timeout(1000)
    result['click_three_boxes'] = await page.evaluate(CLICK_THREE_BOXES)
    await page.wait_for_timeout(1000)
    result['before_confirm'] = await page.evaluate(READ)
    result['confirm_cover'] = await page.evaluate(CONFIRM_COVER)
    await page.wait_for_timeout(3000)
    result['after_confirm'] = await page.evaluate(READ)

    (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / 'after_confirm.png'), full_page=True)
    print(json.dumps({'status':'kept_alive','result_path': str(outdir / 'result.json')}, ensure_ascii=False))
    while True:
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

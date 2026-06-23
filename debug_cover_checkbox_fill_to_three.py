from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import extract_docx_images, list_docx
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
  const textOf = el => (el.innerText || el.textContent || '').trim();
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = textOf(el);
    const aria = el.getAttribute?.('aria-label') || '';
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === '选择封面') score += 320;
    if (t === '更换') score += 220;
    if (/更换封面/.test(aria)) score += 260;
    return {el, score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.score > 0 && x.rect.w > 10 && x.rect.h > 10).sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return false;
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return true;
}'''

SELECT_THREE = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a,input[type=radio]'));
  const rows = [];
  for (const el of els) {
    const wrap = el.closest('label,div,span,button') || el;
    const t = (wrap.innerText || wrap.textContent || '').trim();
    const r = wrap.getBoundingClientRect();
    let score = 0;
    if (t === '三图') score += 300;
    if (t.includes('三图')) score += 150;
    if (el.tagName === 'INPUT' && el.getAttribute('type') === 'radio' && el.getAttribute('value') === 'three') score += 250;
    if (score > 0 && r.width > 10 && r.height > 10) rows.push({el: wrap, score, t, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(wrap.className||'')});
  }
  rows.sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, score:picked.score, cls:picked.cls, rect:picked.rect}};
}'''

FILL_TO_THREE = r'''() => {
  const list = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => {
    const wrap = el.closest('label,div,span,li') || el;
    const r = wrap.getBoundingClientRect();
    return {i, el, wrap, checked: !!el.checked, disabled: !!el.disabled, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(wrap.className||''), text:(wrap.innerText||wrap.textContent||'').trim().slice(0,80)};
  }).filter(x => !x.disabled);
  const checked = list.filter(x => x.checked);
  const unchecked = list.filter(x => !x.checked);
  const need = Math.max(0, 3 - checked.length);
  const clicked = [];
  for (const item of unchecked.slice(0, need)) {
    const r = item.rect;
    if (typeof item.wrap.click === 'function') item.wrap.click();
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      item.wrap.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
    }
    clicked.push({i:item.i, rect:item.rect, cls:item.cls, text:item.text});
  }
  const after = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked: !!el.checked, disabled: !!el.disabled}));
  return {ok:true, beforeChecked: checked.map(x => x.i), unchecked: unchecked.map(x => x.i), need, clicked, after};
}'''

CONFIRM = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.filter(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return /^确定(\s*\(\d+\))?$/.test(t) && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
  }).map(el => {
    const r = el.getBoundingClientRect();
    const cls = String(el.className || '');
    const score = (cls.includes('primary') ? 100 : 0) + r.y;
    return {el, text:(el.innerText||el.textContent||'').trim(), cls, score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).sort((a,b) => b.score - a.score);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.map(x => ({text:x.text, cls:x.cls, score:x.score, rect:x.rect}))};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{text:picked.text, cls:picked.cls, score:picked.score, rect:picked.rect}};
}'''

READ = r'''() => ({
  bodyText: (document.body.innerText || '').slice(0, 5000),
  checkboxStates: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked: !!el.checked, disabled: !!el.disabled})).slice(0, 50)
})'''


async def main():
    outdir = base / 'debug' / 'cover_checkbox_fill_to_three'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]
    images = extract_docx_images(docx, outdir / 'covers')

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_cover_fill_{int(time.time())}'),
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

        result = {'image_count': len(images)}
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
        result['fill_to_three'] = await page.evaluate(FILL_TO_THREE)
        await page.wait_for_timeout(1000)
        result['confirm_cover'] = await page.evaluate(CONFIRM)
        await page.wait_for_timeout(4000)
        result['final'] = await page.evaluate(READ)

        await page.screenshot(path=str(outdir / 'final.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({'status':'kept_alive','result_path': str(outdir / 'result.json')}, ensure_ascii=False))
        while True:
            await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

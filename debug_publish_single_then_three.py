from __future__ import annotations

import asyncio
import json
import re
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

OPEN_INSERT = r'''() => {
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  if (!entry) return {ok:false, error:'insert entry not found'};
  const r = entry.getBoundingClientRect();
  const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  return {ok:true, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(entry.className||''), text:(entry.innerText||entry.textContent||'').trim()};
}'''

CLICK_IMPORT_FIXED = r'''() => {
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const picked = items.length >= 8 ? items[7] : null;
  if (!picked) return {ok:false, count:items.length};
  const r = picked.getBoundingClientRect();
  const fire = type => picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
  return {ok:true, count:items.length, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, txt:(picked.innerText||picked.textContent||'').trim(), cls:String(picked.className||'')};
}'''

DISMISS = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span'));
  const out = [];
  for (const el of els) {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    if (!(r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0)) continue;
    if (t === '我知道了' || t === '下一步' || String(el.className || '').includes('cheetah-tour-close')) {
      if (typeof el.click === 'function') el.click();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
      out.push({text:t, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}});
    }
  }
  return out;
}'''

CONFIRM_JS = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.filter(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return /^确定(\s*\(\d+\))?$/.test(t) && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
  }).map(el => {
    const r = el.getBoundingClientRect();
    return {el, text:(el.innerText||el.textContent||'').trim(), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  });
  const picked = rows.sort((a,b) => (b.cls.includes('primary')?1:0) - (a.cls.includes('primary')?1:0) || b.rect.y - a.rect.y)[0];
  if (!picked) return {ok:false, rows: rows.map(x => ({text:x.text, cls:x.cls, rect:x.rect}))};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{text:picked.text, cls:picked.cls, rect:picked.rect}, rows: rows.map(x => ({text:x.text, cls:x.cls, rect:x.rect}))};
}'''

OPEN_COVER_REACT = r'''() => {
  const item = document.querySelector('.FeEditorApp-_93c3fe2a3121c388-item');
  if (!item) return {ok:false, error:'no cover item'};
  const key = Object.keys(item).find(k => k.startsWith('__reactProps$'));
  const props = key ? item[key] : null;
  const child = props?.children?.[0];
  const open = child?.props?.open;
  if (typeof open !== 'function') return {ok:false, error:'no open fn', key, childProps: child?.props ? Object.keys(child.props) : []};
  const ret = open();
  return {ok:true, key, retType: typeof ret, childProps: Object.keys(child.props || {})};
}'''

SWITCH_MODE = r'''(modeValue) => {
  const input = document.querySelector(`input.cheetah-radio-input[name="cover"][value="${modeValue}"]`);
  const label = input ? input.closest('label') : null;
  const target = label || input;
  if (!target) return {ok:false};
  const r = target.getBoundingClientRect();
  if (input) {
    input.checked = true;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }
  if (typeof target.click === 'function') target.click();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    target.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  }
  return {
    rect: {x:r.x,y:r.y,w:r.width,h:r.height},
    text: (target.innerText || target.textContent || '').trim(),
    radioState: Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked})),
  };
}'''

PICK_COVER = r'''(wanted) => {
  const checks = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => {
    const wrap = el.closest('label,div,span,li') || el;
    const r = wrap.getBoundingClientRect();
    return { i, el, wrap, checked: !!el.checked, disabled: !!el.disabled, rect: {x:r.x,y:r.y,w:r.width,h:r.height}, text: (wrap.innerText || wrap.textContent || '').trim().slice(0, 100), cls: String(wrap.className || '') };
  }).filter(x => !x.disabled && x.rect.w > 5 && x.rect.h > 5);
  const checkedBefore = checks.filter(x => x.checked).map(x => x.i);
  const need = Math.max(0, wanted - checkedBefore.length);
  const clicked = [];
  for (const item of checks.filter(x => !x.checked).sort((a,b) => a.rect.y - b.rect.y || a.rect.x - b.rect.x).slice(0, need)) {
    const r = item.rect;
    try { if (typeof item.wrap.click === 'function') item.wrap.click(); } catch (_) {}
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      item.wrap.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 }));
    }
    clicked.push({i:item.i, text:item.text, cls:item.cls, rect:item.rect});
  }
  return {
    checkedBefore,
    clicked,
    checkedAfter: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({ i, checked: !!el.checked, disabled: !!el.disabled })),
  };
}'''

PUBLISH_JS = r'''() => {
  const isPublish = el => (el.innerText || el.value || el.textContent || '').trim() === '发布';
  const candidates = Array.from(document.querySelectorAll('button.cheetah-btn, button, .op-btn-outter-content'))
    .filter(isPublish)
    .map(el => {
      const r = el.getBoundingClientRect();
      const cls = String(el.className || '');
      const score = (el.tagName === 'BUTTON' ? 100 : 0) + (cls.includes('cheetah-btn-primary') ? 80 : 0) + (cls.includes('cheetah-btn-solid') ? 30 : 0) + (r.y > window.innerHeight * 0.55 ? 60 : 0) + (r.width >= 70 && r.height >= 30 ? 20 : 0) - (r.y < window.innerHeight * 0.35 ? 80 : 0);
      return {el, r, cls, score};
    })
    .filter(x => x.r.width > 20 && x.r.height > 20 && x.r.x >= 0 && x.r.y >= 0)
    .sort((a, b) => b.score - a.score || b.r.y - a.r.y);
  const picked = candidates[0];
  if (!picked) return null;
  const el = picked.el;
  const r = picked.r;
  const detail = {text:(el.innerText || el.value || el.textContent || '').trim(), tag: el.tagName, cls:picked.cls, score:picked.score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  try { el.focus({preventScroll: true}); } catch (_) {}
  if (typeof el.click === 'function') el.click();
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return detail;
}'''

CLICK_CONFIRM_TEXT = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const visible = els.filter(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return t === '确认' && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
  });
  const el = visible[visible.length - 1];
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (typeof el.click === 'function') el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {text:(el.innerText||el.textContent||'').trim(), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

STATE = r'''() => ({
  url: location.href,
  body: (document.body.innerText || '').slice(0, 8000),
  publishBtns: Array.from(document.querySelectorAll('button,[role=button],div,span,a')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return {t, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.t && /发布|确认|成功|返回编辑|立即发布|继续创作|查看文章|已发布|审核/.test(x.t)).slice(0,120)
})'''

async def run_one(page, docx: Path, outdir: Path, wanted: int):
    result = {'docx': str(docx), 'wanted': wanted}
    await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_function("() => !!document.querySelector('#ueditor_0') && !!document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry, #edui41_state')", timeout=120000)
    await page.wait_for_timeout(7000)
    result['dismiss'] = await page.evaluate(DISMISS)
    await page.wait_for_timeout(1200)
    result['open_insert'] = await page.evaluate(OPEN_INSERT)
    await page.wait_for_timeout(1000)
    result['click_import'] = await page.evaluate(CLICK_IMPORT_FIXED)
    await page.wait_for_timeout(1000)
    locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
    await locator.set_input_files(str(docx))
    await page.wait_for_timeout(4000)
    result['confirm_import'] = await page.evaluate(CONFIRM_JS)
    await page.wait_for_timeout(5000)
    mode = 'three' if wanted >= 3 else 'one'
    result['switch_mode'] = await page.evaluate(SWITCH_MODE, mode)
    await page.wait_for_timeout(1200)
    result['open_cover'] = await page.evaluate(OPEN_COVER_REACT)
    await page.wait_for_timeout(2500)
    result['pick_cover'] = await page.evaluate(PICK_COVER, wanted)
    await page.wait_for_timeout(1200)
    result['confirm_cover'] = await page.evaluate(CONFIRM_JS)
    await page.wait_for_timeout(3000)
    result['publish_click'] = await page.evaluate(PUBLISH_JS)
    await page.wait_for_timeout(2500)
    result['publish_confirm'] = await page.evaluate(CLICK_CONFIRM_TEXT)
    await page.wait_for_timeout(5000)
    result['state'] = await page.evaluate(STATE)
    (outdir / f'{docx.stem}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / f'{docx.stem}.png'), full_page=True)
    body = result['state']['body']
    success = any(k in body for k in ['发布成功', '已发布', '查看文章', '继续创作', '审核'])
    return result, success

async def main():
    outdir = base / 'debug' / 'publish_single_then_three'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    single = None
    three = None
    for f in files:
        c = len(extract_docx_images(f, outdir / ('covers_' + re.sub(r'[^\w\-]+', '_', f.stem))))
        if c == 1 and single is None:
            single = f
        if c >= 3 and three is None:
            three = f
        if single and three:
            break
    targets = []
    if single:
        targets.append((single, 1))
    if three:
        targets.append((three, 3))

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_publish_single_then_three_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1400, 'height': 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        summary = []
        for docx, wanted in targets:
            result, success = await run_one(page, docx, outdir, wanted)
            summary.append({'docx': str(docx), 'wanted': wanted, 'success': success, 'url': result['state']['url']})
            if not success:
                break
            await page.wait_for_timeout(3000)
        (outdir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

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

PREPARE = r'''() => {
  const clickBest = (pred) => {
    const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a,input[type=radio]'));
    const rows = [];
    for (const el of els) {
      const wrap = el.closest('label,div,span,button,a') || el;
      const t = (wrap.innerText || wrap.textContent || '').trim();
      const aria = wrap.getAttribute?.('aria-label') || '';
      const r = wrap.getBoundingClientRect();
      if (!(r.width > 10 && r.height > 10)) continue;
      const score = pred(t, aria, el, wrap, r) || 0;
      if (score > 0) rows.push({el: wrap, t, aria, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score, cls:String(wrap.className||'')});
    }
    rows.sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
    const picked = rows[0];
    if (!picked) return null;
    const r = picked.rect;
    if (typeof picked.el.click === 'function') picked.el.click();
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
    }
    return {t:picked.t, cls:picked.cls, aria:picked.aria, score:picked.score, rect:picked.rect};
  };

  const openCover = clickBest((t, aria) => (t === '选择封面' ? 320 : 0) + (t === '更换' ? 220 : 0) + (/更换封面/.test(aria) ? 260 : 0));
  const three = clickBest((t, aria, el) => (t === '三图' ? 300 : 0) + (t.includes('三图') ? 150 : 0) + (el.tagName === 'INPUT' && el.getAttribute('type') === 'radio' && el.getAttribute('value') === 'three' ? 250 : 0));

  const boxes = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]'));
  for (const el of boxes.slice(0, 3)) {
    if (!el.checked) {
      const r = el.getBoundingClientRect();
      if (typeof el.click === 'function') el.click();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
    }
  }
  return {
    openCover,
    three,
    checkboxStates: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked: !!el.checked, disabled: !!el.disabled}))
  };
}'''

SCOPED_CONFIRM = r'''() => {
  const nodes = Array.from(document.querySelectorAll('*')).map((el, i) => {
    const t = (el.innerText || el.textContent || '').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    return {el, i, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.rect.w > 20 && x.rect.h > 20 && x.rect.y > 600);

  const coverArea = nodes.filter(x => /选择封面|三图|单图|优质封面|查看封面展示页面/.test(x.t)).sort((a,b) => a.rect.y - b.rect.y)[0];
  const coverY = coverArea ? coverArea.rect.y : 700;

  const candidates = nodes.filter(x => {
    if (x.rect.y < coverY - 50 || x.rect.y > coverY + 500) return false;
    if (/存草稿|预览|定时发布|发布/.test(x.t)) return false;
    if (/^确定(\s*\(\d+\))?$/.test(x.t)) return true;
    if (x.t === '确认' || x.t === '完成' || x.t === '应用' || x.t === '保存') return true;
    if (/primary/.test(x.cls) && x.rect.y > coverY) return true;
    return false;
  }).map(x => {
    let score = 0;
    if (/^确定(\s*\(\d+\))?$/.test(x.t)) score += 500;
    if (x.t === '确认') score += 420;
    if (x.t === '完成') score += 360;
    if (x.t === '应用' || x.t === '保存') score += 260;
    if (/primary/.test(x.cls)) score += 120;
    score += Math.max(0, 500 - Math.abs(x.rect.y - coverY));
    return {...x, score};
  }).sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);

  const picked = candidates[0];
  if (!picked) {
    return {ok:false, coverArea: coverArea ? {t:coverArea.t, cls:coverArea.cls, rect:coverArea.rect} : null, candidates: candidates.slice(0,20).map(x => ({t:x.t, cls:x.cls, score:x.score, rect:x.rect}))};
  }
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, coverArea: coverArea ? {t:coverArea.t, cls:coverArea.cls, rect:coverArea.rect} : null, picked:{t:picked.t, cls:picked.cls, score:picked.score, rect:picked.rect}, candidates:candidates.slice(0,10).map(x => ({t:x.t, cls:x.cls, score:x.score, rect:x.rect}))};
}'''

READ = r'''() => ({
  bodyText: (document.body.innerText || '').slice(0, 8000),
  checkboxStates: Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({i, checked: !!el.checked, disabled: !!el.disabled})).slice(0, 50),
  nearCover: Array.from(document.querySelectorAll('*')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    return {t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.t && x.rect.w > 20 && x.rect.h > 20 && x.rect.y > 600 && x.rect.y < 1400).slice(0, 200)
})'''

async def main():
    outdir = base / 'debug' / 'cover_confirm_scoped'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(base / f'edge_profile_cover_scoped_{int(time.time())}'),
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

    result['prepare'] = await page.evaluate(PREPARE)
    await page.wait_for_timeout(1200)
    result['before_scoped_confirm'] = await page.evaluate(READ)
    result['scoped_confirm'] = await page.evaluate(SCOPED_CONFIRM)
    await page.wait_for_timeout(3000)
    result['after_scoped_confirm'] = await page.evaluate(READ)

    (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / 'after_scoped_confirm.png'), full_page=True)
    print(json.dumps({'status':'kept_alive','result_path': str(outdir / 'result.json')}, ensure_ascii=False))
    while True:
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

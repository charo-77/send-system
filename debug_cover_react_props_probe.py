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
  return true;
}'''

PROPS = r'''() => {
  const item = document.querySelector('.FeEditorApp-_93c3fe2a3121c388-item');
  if (!item) return null;
  const keys = Object.keys(item).filter(k => k.startsWith('__reactProps$') || k.startsWith('__reactFiber$'));
  const key = keys.find(k => k.startsWith('__reactProps$')) || keys[0];
  const props = key ? item[key] : null;
  const out = { key, propKeys: props ? Object.keys(props) : [] };
  if (props) {
    out.propTypes = Object.fromEntries(Object.entries(props).map(([k,v]) => [k, typeof v]));
    out.onClickType = typeof props.onClick;
    out.childrenType = typeof props.children;
    out.open = {};
    try {
      if (typeof props.onClick === 'function') {
        out.open.onClickResult = props.onClick({type:'probe'});
      }
    } catch (e) {
      out.open.onClickError = String(e);
    }
    try {
      if (typeof props.children === 'function') {
        out.open.childrenResultType = typeof props.children();
      }
    } catch (e) {
      out.open.childrenError = String(e);
    }
    out.raw = JSON.stringify(props, (k, v) => typeof v === 'function' ? '[fn]' : v, 2).slice(0, 5000);
  }
  return out;
}'''

FIND_HANDLERS = r'''() => {
  const item = document.querySelector('.FeEditorApp-_93c3fe2a3121c388-item');
  if (!item) return null;
  const walk = (obj, depth = 0, seen = new WeakSet()) => {
    if (!obj || typeof obj !== 'object' || depth > 5 || seen.has(obj)) return [];
    seen.add(obj);
    const out = [];
    for (const k of Object.keys(obj)) {
      try {
        const v = obj[k];
        const t = typeof v;
        if (t === 'function') out.push({k, t});
        else if (v && t === 'object') out.push(...walk(v, depth + 1, seen).map(x => ({k: k + '.' + x.k, t: x.t})));
      } catch (_) {}
    }
    return out;
  };
  const keys = Object.keys(item).filter(k => k.startsWith('__reactProps$') || k.startsWith('__reactFiber$'));
  const obj = keys.map(k => item[k]).find(Boolean);
  return {
    keys,
    functions: obj ? walk(obj).slice(0, 200) : [],
  };
}'''

async def main():
    outdir = base / 'debug' / 'cover_react_props_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_cover_react_props_{int(time.time())}'),
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
        await page.evaluate(SWITCH_THREE)
        await page.wait_for_timeout(1500)
        result = await page.evaluate(PROPS)
        handlers = await page.evaluate(FIND_HANDLERS)
        (outdir / 'result.json').write_text(json.dumps({'props': result, 'handlers': handlers}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'result_path': str(outdir / 'result.json'), 'hasProps': bool(result), 'handlerCount': len(handlers.get('functions', [])) if handlers else 0}, ensure_ascii=False))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

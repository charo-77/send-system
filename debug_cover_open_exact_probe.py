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

OPEN_COVER_EXACT = r'''() => {
  const root = document.querySelector('#bjhNewsCover');
  if (!root) return {ok:false, error:'no #bjhNewsCover'};
  const card = root.querySelector('.FeEditorApp-_73a3a52aab7e3a36-default, .FeEditorApp-_73a3a52aab7e3a36-content, .FeEditorApp-_93c3fe2a3121c388-item');
  if (!card) return {ok:false, error:'no cover card'};
  const r = card.getBoundingClientRect();
  try { card.scrollIntoView({block:'center'}); } catch (_) {}
  if (typeof card.click === 'function') card.click();
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    card.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {ok:true, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(card.className||''), txt:(card.innerText||card.textContent||'').trim()};
}'''

SNAP = r'''() => {
  const text = (document.body.innerText || '');
  const confirms = Array.from(document.querySelectorAll('button,[role=button],div,span,a')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return {t, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => /^确定(\s*\(\d+\))?$/.test(x.t) || /取消|完成|确认|图库|上传|封面/.test(x.t)).slice(0,200);

  const checkboxes = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => {
    const r = el.getBoundingClientRect();
    return {i, checked:!!el.checked, disabled:!!el.disabled, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:(el.outerHTML||'').slice(0,200)};
  });

  const dialogs = Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="modal"], [class*="drawer"], [class*="popup"], [class*="popover"]')).map((el, i) => {
    const r = el.getBoundingClientRect();
    return {i, cls:String(el.className||'').slice(0,200), txt:(el.innerText||'').slice(0,500), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.rect.w > 40 && x.rect.h > 20);

  return {
    bodySnippet: text.slice(0, 8000),
    confirms,
    checkboxes,
    dialogs,
    radioState: Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked})),
  };
}'''

async def main():
    outdir = base / 'debug' / 'cover_open_exact_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_cover_open_exact_{int(time.time())}'),
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
        open_result = await page.evaluate(OPEN_COVER_EXACT)
        await page.wait_for_timeout(3000)
        snap = await page.evaluate(SNAP)
        (outdir / 'result.json').write_text(json.dumps({'open_result': open_result, 'snap': snap}, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(outdir / 'after_open_exact.png'), full_page=True)
        print(json.dumps({'open_result': open_result, 'result_path': str(outdir / 'result.json')}, ensure_ascii=False))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

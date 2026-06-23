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

DISMISS = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span'));
  for (const el of els) {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    if (!(r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0)) continue;
    if (t === '我知道了' || t === '下一步' || String(el.className || '').includes('cheetah-tour-close')) {
      try { if (typeof el.click === 'function') el.click(); } catch (_) {}
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
    }
  }
  return true;
}'''

OPEN_INSERT = r'''() => {
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state') || document.querySelector('#edui41');
  if (!entry) return {ok:false, error:'insert entry not found'};
  const r = entry.getBoundingClientRect();
  const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  return {ok:true, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(entry.className||''), text:(entry.innerText||entry.textContent||'').trim()};
}'''

SCAN = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item')).map((el, i) => ({
    i,
    txt: textOf(el),
    cls: String(el.className || ''),
    rect: rectOf(el),
    hasDocIcon: !!el.querySelector('.l-icon-BjhBasicDaoruwendang'),
    html: (el.outerHTML || '').slice(0, 300),
  }));
  const inputs = Array.from(document.querySelectorAll('input[type=file]')).map((el, i) => ({
    i,
    accept: el.getAttribute('accept') || '',
    name: el.getAttribute('name') || '',
    cls: String(el.className || ''),
    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
    rect: rectOf(el),
    html: (el.outerHTML || '').slice(0, 240),
  }));
  const importNodes = Array.from(document.querySelectorAll('*')).map((el, i) => ({
    i,
    tag: el.tagName,
    txt: textOf(el).slice(0,120),
    cls: String(el.className || ''),
    id: el.id || '',
    rect: rectOf(el),
    html: (el.outerHTML || '').slice(0, 220),
  })).filter(x => x.rect.w > 10 && x.rect.h > 10 && /导入文档|插入|Daoruwendang|importdoc|edui41|edui42|drawer|popup|modal/.test(x.txt + ' ' + x.cls + ' ' + x.id + ' ' + x.html)).slice(0,200);
  return {
    url: location.href,
    body: (document.body.innerText || '').slice(0, 5000),
    items,
    inputs,
    importNodes,
  };
}'''

CLICK_ITEM = r'''() => {
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const picked = items.find(el => el.querySelector('.l-icon-BjhBasicDaoruwendang')) || items.find(el => /导入文档/.test((el.innerText || el.textContent || '').trim())) || null;
  if (!picked) return {ok:false, count:items.length};
  const r = picked.getBoundingClientRect();
  try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
  for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  }
  return {ok:true, count:items.length, txt:(picked.innerText||picked.textContent||'').trim(), cls:String(picked.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

PUBLISH = r'''() => {
  const isPublish = el => (el.innerText || el.value || el.textContent || '').trim() === '发布';
  const candidates = Array.from(document.querySelectorAll('button.cheetah-btn, button, .op-btn-outter-content'))
    .filter(isPublish)
    .map(el => {
      const r = el.getBoundingClientRect();
      const cls = String(el.className || '');
      const score = (el.tagName === 'BUTTON' ? 100 : 0) + (cls.includes('cheetah-btn-primary') ? 80 : 0) + (cls.includes('cheetah-btn-solid') ? 30 : 0) + (r.y > window.innerHeight * 0.55 ? 60 : 0);
      return {el, r, cls, score};
    }).filter(x => x.r.width > 20 && x.r.height > 20 && x.r.x >= 0 && x.r.y >= 0).sort((a, b) => b.score - a.score || b.r.y - a.r.y);
  const picked = candidates[0];
  if (!picked) return null;
  const r = picked.r;
  try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {text:(picked.el.innerText||picked.el.textContent||'').trim(), cls:picked.cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

CLICK_CONFIRM = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const el = els.filter(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return t === '确认' && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
  }).slice(-1)[0];
  if (!el) return null;
  const r = el.getBoundingClientRect();
  try { if (typeof el.click === 'function') el.click(); } catch (_) {}
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  }
  return {text:(el.innerText||el.textContent||'').trim(), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

STATE = r'''() => ({
  url: location.href,
  body: (document.body.innerText || '').slice(0, 8000),
  texts: Array.from(document.querySelectorAll('button,[role=button],div,span,a')).map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const r = el.getBoundingClientRect();
    return {t, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.t && /发布|确认|成功|返回编辑|立即发布|继续创作|查看文章|已发布|审核|标题|正文/.test(x.t)).slice(0,160)
})'''

async def main():
    outdir = base / 'debug' / 'publish_single_only_keep_open'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')

    single = None
    for f in files:
        c = len(extract_docx_images(f, outdir / ('covers_' + re.sub(r'[^\w\-]+', '_', f.stem))))
        if c == 1:
            single = f
            break
    if single is None:
        raise SystemExit('no single-image docx found')

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(base / f'edge_profile_publish_single_only_{int(time.time())}'),
        channel='msedge',
        headless=False,
        viewport={'width': 1400, 'height': 900},
        args=['--disable-blink-features=AutomationControlled'],
    )
    await inject_cookies(context, cookies)
    page = context.pages[0] if context.pages else await context.new_page()

    result = {'docx': str(single)}
    await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_function("() => !!document.querySelector('#ueditor_0') && !!document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry, #edui41_state, #edui41')", timeout=120000)
    await page.wait_for_timeout(7000)
    await page.evaluate(DISMISS)
    await page.wait_for_timeout(1200)

    scan_before = await page.evaluate(SCAN)
    result['scan_before'] = scan_before

    import_clicked = False
    for attempt in range(1, 6):
        result[f'open_insert_{attempt}'] = await page.evaluate(OPEN_INSERT)
        await page.wait_for_timeout(1200)
        result[f'scan_after_open_{attempt}'] = await page.evaluate(SCAN)
        click_res = await page.evaluate(CLICK_ITEM)
        result[f'click_item_{attempt}'] = click_res
        await page.wait_for_timeout(1500)
        scan_after_click = await page.evaluate(SCAN)
        result[f'scan_after_click_{attempt}'] = scan_after_click
        docx_inputs = [x for x in scan_after_click.get('inputs', []) if '.docx' in (x.get('accept') or '').lower() or x.get('name') == 'file']
        if click_res.get('ok') or docx_inputs:
            import_clicked = True
            break

    if import_clicked:
        try:
            locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
            await locator.set_input_files(str(single), timeout=10000)
            result['set_input_files'] = {'ok': True}
            await page.wait_for_timeout(4000)
        except Exception as e:
            result['set_input_files'] = {'ok': False, 'error': str(e)}
    else:
        result['set_input_files'] = {'ok': False, 'error': 'import entry not opened'}

    result['final_scan'] = await page.evaluate(SCAN)
    result['final_state'] = await page.evaluate(STATE)
    (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / 'current.png'), full_page=True)
    print(json.dumps({'status':'kept_alive','docx':str(single),'set_input_files':result['set_input_files']}, ensure_ascii=False))
    while True:
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

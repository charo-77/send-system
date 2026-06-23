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

OPEN_INSERT = r'''() => {
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  if (!entry) return {ok:false, error:'insert entry not found'};
  const r = entry.getBoundingClientRect();
  const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  return {ok:true};
}'''

CLICK_IMPORT = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const picked = items.find(el => el.querySelector('.l-icon-BjhBasicDaoruwendang')) || items.find(el => /导入文档/.test(textOf(el))) || null;
  if (!picked) return {ok:false, count: items.length};
  const r = picked.getBoundingClientRect();
  const fire = type => picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
  return {ok:true, text:textOf(picked), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}'''

OPEN_COVER = r'''() => {
  const textOf = el => (el.innerText || el.textContent || '').trim();
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = textOf(el);
    const cls = String(el.className || '');
    const aria = el.getAttribute?.('aria-label') || '';
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === '更换') score += 220;
    if (t === '编辑') score += 120;
    if (/更换封面/.test(aria)) score += 260;
    if (/设置封面|选择封面/.test(t)) score += 160;
    if (/cover|Cover/.test(cls)) score += 80;
    if (r.y > 900 && r.y < 1150) score += 60;
    return {el, t, cls, aria, score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.score > 0 && x.rect.w > 10 && x.rect.h > 10).sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.map(x => ({t:x.t, cls:x.cls, aria:x.aria, score:x.score, rect:x.rect}))};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, aria:picked.aria, score:picked.score, rect:picked.rect}, rows: rows.map(x => ({t:x.t, cls:x.cls, aria:x.aria, score:x.score, rect:x.rect}))};
}'''

SELECT_THREE = r'''() => {
  const textOf = el => (el.innerText || el.textContent || '').trim();
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = textOf(el);
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === '三图') score += 300;
    if (/三图/.test(t)) score += 180;
    if (/cover|Cover/.test(cls)) score += 40;
    return {el, t, cls, score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.score > 0 && x.rect.w > 10 && x.rect.h > 10).sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.map(x => ({t:x.t, cls:x.cls, score:x.score, rect:x.rect}))};
  const r = picked.rect;
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, score:picked.score, rect:picked.rect}, rows: rows.map(x => ({t:x.t, cls:x.cls, score:x.score, rect:x.rect}))};
}'''

PICK_IMAGES = r'''(pickCount) => {
  const imgs = Array.from(document.querySelectorAll('img')).filter(img => {
    const r = img.getBoundingClientRect();
    const src = img.getAttribute('src') || '';
    return r.width > 40 && r.height > 40 && src && !src.startsWith('data:');
  });
  const chosen = imgs.slice(0, pickCount);
  const out = [];
  for (const img of chosen) {
    const box = img.closest('label,li,div,button') || img;
    const r = box.getBoundingClientRect();
    if (typeof box.click === 'function') box.click();
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      box.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
    }
    out.push({src: img.getAttribute('src') || '', cls:String(box.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}});
  }
  return {ok: out.length > 0, picked: out, candidateCount: imgs.length};
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
  return {ok:true, picked:{text:picked.text, cls:picked.cls, score:picked.score, rect:picked.rect}, rows: rows.map(x => ({text:x.text, cls:x.cls, score:x.score, rect:x.rect}))};
}'''

READ = r'''() => ({
  bodyText: (document.body.innerText || '').slice(0, 5000),
  fileInputs: Array.from(document.querySelectorAll('input[type=file], input')).map((el, i) => ({
    i, type: el.getAttribute('type') || '', accept: el.getAttribute('accept') || '', name: el.getAttribute('name') || '', cls: String(el.className || ''), html: (el.outerHTML || '').slice(0, 220)
  })).slice(0, 100)
})'''


async def main():
    outdir = base / 'debug' / 'cover_execute_after_import'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]
    images = extract_docx_images(docx, outdir / 'covers')
    pick_count = 3 if len(images) >= 3 else 1 if len(images) >= 1 else 0

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_cover_exec_{int(time.time())}'),
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
        result['dismiss'] = await page.evaluate(DISMISS)
        await page.wait_for_timeout(1200)

        await page.evaluate(OPEN_INSERT)
        await page.wait_for_timeout(800)
        for _ in range(25):
            click_import = await page.evaluate(CLICK_IMPORT)
            if click_import.get('ok'):
                result['click_import'] = click_import
                break
            await page.wait_for_timeout(200)
        locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
        await locator.set_input_files(str(docx))
        result['after_upload'] = await page.evaluate(READ)
        await page.wait_for_timeout(5000)

        result['open_cover'] = await page.evaluate(OPEN_COVER)
        await page.wait_for_timeout(2000)
        result['select_three'] = await page.evaluate(SELECT_THREE)
        await page.wait_for_timeout(1500)
        result['pick_images'] = await page.evaluate(PICK_IMAGES, pick_count)
        await page.wait_for_timeout(1500)
        result['confirm_cover'] = await page.evaluate(CONFIRM)
        await page.wait_for_timeout(4000)
        result['final'] = await page.evaluate(READ)

        await page.screenshot(path=str(outdir / 'final.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'docx': str(docx),
            'image_count': len(images),
            'pick_count': pick_count,
            'click_import': result.get('click_import'),
            'open_cover': result.get('open_cover'),
            'select_three': result.get('select_three'),
            'pick_images': result.get('pick_images'),
            'confirm_cover': result.get('confirm_cover'),
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

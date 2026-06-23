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

OPEN_INSERT = r'''() => {
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  if (!entry) return {ok:false, error:'insert entry not found'};
  const r = entry.getBoundingClientRect();
  const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  return {ok:true, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, cls:String(entry.className||''), text:(entry.innerText||entry.textContent||'').trim()};
}'''

CLICK_EXACT_IMPORT = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
  const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item'));
  const rows = items.map((el, i) => {
    const txt = textOf(el);
    const cls = String(el.className || '');
    const html = el.outerHTML || '';
    const hasDocIcon = !!el.querySelector('.l-icon-BjhBasicDaoruwendang');
    const hasLabel = /导入文档/.test(txt) || /导入文档/.test(html);
    return { i, txt, cls, html: html.slice(0, 300), hasDocIcon, hasLabel, rect: rectOf(el) };
  });
  const picked = items.find(el => el.querySelector('.l-icon-BjhBasicDaoruwendang')) || items.find(el => /导入文档/.test(textOf(el))) || null;
  if (!picked) return {ok:false, rows};
  const r = picked.getBoundingClientRect();
  const fire = type => picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  try { picked.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
  try { picked.focus?.({preventScroll:true}); } catch (_) {}
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
  return {
    ok:true,
    picked:{txt:textOf(picked), cls:String(picked.className||''), rect:rectOf(picked), hasDocIcon:!!picked.querySelector('.l-icon-BjhBasicDaoruwendang'), html:(picked.outerHTML||'').slice(0, 300)},
    rows
  };
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
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span'));
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

CHOOSE_COVER = r'''(args) => {
  const mode = args.mode;
  const pickCount = args.pickCount;
  const clickText = (matcher) => {
    const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
    const found = els.find(el => {
      const t = (el.innerText || el.textContent || '').trim();
      const r = el.getBoundingClientRect();
      return matcher(t, el) && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
    });
    if (!found) return null;
    const r = found.getBoundingClientRect();
    if (typeof found.click === 'function') found.click();
    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
      found.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
    }
    return {text:(found.innerText||found.textContent||'').trim(), cls:String(found.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  };
  const open = clickText(t => /编辑|更换|选择封面/.test(t));
  const out = {open};
  if (mode === 'three') out.switchMode = clickText(t => t === '三图');
  else if (mode === 'one') out.switchMode = clickText(t => t === '单图');
  else out.switchMode = clickText(t => /AI.*封面|生成.*封面|智能.*封面/.test(t));

  if (mode !== 'ai') {
    const imgs = Array.from(document.querySelectorAll('img')).filter(img => {
      const r = img.getBoundingClientRect();
      const src = img.getAttribute('src') || '';
      return r.width > 40 && r.height > 40 && src && !src.startsWith('data:');
    }).slice(0, pickCount);
    out.picked = imgs.map(img => {
      const box = img.closest('label,li,div,button') || img;
      const r = box.getBoundingClientRect();
      if (typeof box.click === 'function') box.click();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        box.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
      return {src: img.getAttribute('src') || '', cls:String(box.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
    });
  }
  return out;
}'''

READ_STATE = r'''() => ({
  fileInputs: Array.from(document.querySelectorAll('input[type=file], input')).map((el, i) => ({
    i,
    type: el.getAttribute('type') || '',
    accept: el.getAttribute('accept') || '',
    name: el.getAttribute('name') || '',
    cls: String(el.className || ''),
    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
    html: (el.outerHTML || '').slice(0, 220),
  })).slice(0, 100),
  bodyText: (document.body.innerText || '').slice(0, 5000),
})'''


async def main():
    outdir = base / 'debug' / 'importdoc_execute_full'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]
    images = extract_docx_images(docx, outdir / 'covers')
    image_count = len(images)
    cover_mode = 'three' if image_count >= 3 else 'one' if image_count >= 1 else 'ai'
    pick_count = 3 if image_count >= 3 else 1 if image_count >= 1 else 0

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_execute_full_{int(time.time())}'),
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

        open_ok = None
        exact = None
        for _ in range(4):
            open_ok = await page.evaluate(OPEN_INSERT)
            await page.wait_for_timeout(800)
            for _ in range(25):
                exact = await page.evaluate(CLICK_EXACT_IMPORT)
                if exact.get('ok'):
                    break
                await page.wait_for_timeout(200)
            if exact and exact.get('ok'):
                break
        result['open_insert'] = open_ok
        result['click_exact_import'] = exact

        locator = page.locator('input[type="file"][name="file"][accept*=".docx" i], input[type="file"][accept*=".docx" i]').last
        await locator.set_input_files(str(docx))
        result['upload_set'] = {'ok': True, 'docx': str(docx)}
        await page.wait_for_timeout(4000)
        result['after_upload'] = await page.evaluate(READ_STATE)

        result['confirm_import'] = await page.evaluate(CONFIRM_JS)
        await page.wait_for_timeout(5000)
        result['after_confirm'] = await page.evaluate(READ_STATE)

        result['cover_choose'] = await page.evaluate(CHOOSE_COVER, {'mode': cover_mode, 'pickCount': pick_count})
        await page.wait_for_timeout(2500)
        result['cover_confirm'] = await page.evaluate(CONFIRM_JS)
        await page.wait_for_timeout(4000)
        result['final_state'] = await page.evaluate(READ_STATE)

        await page.screenshot(path=str(outdir / 'final.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'docx': str(docx),
            'image_count': image_count,
            'cover_mode': cover_mode,
            'open_insert': open_ok,
            'click_exact_ok': bool(exact and exact.get('ok')),
            'confirm_import': result['confirm_import'],
            'cover_confirm': result['cover_confirm'],
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

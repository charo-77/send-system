from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / 'ck.txt'
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1'

INIT = r'''() => {
  if (window.__importProbeInstalled) return true;
  window.__importProbeInstalled = true;
  window.__importProbeLog = [];
  const log = (type, data) => { try { window.__importProbeLog.push({t:Date.now(), type, data}); } catch (_) {} };
  const desc = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
    return {
      tag: el.tagName || null,
      id: el.id || '',
      cls: String(el.className || ''),
      type: el.getAttribute ? (el.getAttribute('type') || '') : '',
      accept: el.getAttribute ? (el.getAttribute('accept') || '') : '',
      name: el.getAttribute ? (el.getAttribute('name') || '') : '',
      txt: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: (el.outerHTML || '').slice(0, 280),
      parentCls: String(el.parentElement?.className || ''),
    };
  };

  const origCreate = Document.prototype.createElement;
  Document.prototype.createElement = function(tagName, options) {
    const el = origCreate.call(this, tagName, options);
    try {
      if (String(tagName).toLowerCase() === 'input') {
        queueMicrotask(() => log('createElement:input', desc(el)));
        const origSetAttribute = el.setAttribute?.bind(el);
        if (origSetAttribute && !el.__wrappedSetAttribute) {
          el.__wrappedSetAttribute = true;
          el.setAttribute = function(name, value) {
            const res = origSetAttribute(name, value);
            if (/type|accept|name/i.test(String(name))) {
              log('input:setAttribute', {name, value, desc: desc(el)});
            }
            return res;
          };
        }
      }
    } catch (_) {}
    return el;
  };

  const origInputClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function(...args) {
    try { log('input.click', desc(this)); } catch (_) {}
    return origInputClick.apply(this, args);
  };

  const origShowPicker = HTMLInputElement.prototype.showPicker;
  if (origShowPicker) {
    HTMLInputElement.prototype.showPicker = function(...args) {
      try { log('input.showPicker', desc(this)); } catch (_) {}
      return origShowPicker.apply(this, args);
    };
  }

  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes || []) {
        if (!(node instanceof Element)) continue;
        log('dom:add', desc(node));
        if (node.matches?.('input, input[type=file]')) log('dom:add:input', desc(node));
        const inner = node.querySelectorAll?.('input, input[type=file]') || [];
        inner.forEach(el => log('dom:add:input:desc', desc(el)));
        const interesting = node.querySelectorAll?.('*') || [];
        interesting.forEach(el => {
          const blob = [el.id, el.className, el.innerText || '', el.outerHTML || ''].join(' ');
          if (/导入文档|Daoruwendang|file|upload|doc|word|drawer|dialog|modal|popover|portal/i.test(blob)) {
            log('dom:add:interesting', desc(el));
          }
        });
      }
    }
  });
  mo.observe(document.documentElement || document.body, { childList: true, subtree: true });
  log('installed', {url: location.href});
  return true;
}'''

OPEN_MENU = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  if (!entry) return {ok:false, error:'insert entry not found'};
  const r = entry.getBoundingClientRect();
  const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  return {ok:true, entry:{txt:textOf(entry), cls:String(entry.className||''), rect:rectOf(entry)}};
}'''

CLICK_IMPORT = r'''() => {
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; };
  const all = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item, div, button, span, a'));
  const candidates = all.map(el => {
    const txt = textOf(el);
    const cls = String(el.className || '');
    const html = el.outerHTML || '';
    const score = (/导入文档/.test(txt) ? 300 : 0)
      + (/BjhBasicDaoruwendang/.test(cls + ' ' + html) ? 220 : 0)
      + (/9d63bce81e3a0b19-item/.test(cls) ? 80 : 0);
    return {el, txt, cls, html, score, rect: rectOf(el)};
  }).filter(x => x.score >= 300 && x.rect.w > 10 && x.rect.h > 10)
    .sort((a,b) => b.score - a.score || a.rect.y - b.rect.y || a.rect.x - b.rect.x);

  const picked = candidates[0];
  if (!picked) return {ok:false, candidates: candidates.slice(0,20).map(x => ({txt:x.txt, cls:x.cls, rect:x.rect, score:x.score}))};
  const el = picked.el;
  const r = el.getBoundingClientRect();
  const fire = type => el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
  try { el.focus?.({preventScroll:true}); } catch (_) {}
  ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  try { if (typeof el.click === 'function') el.click(); } catch (_) {}
  return {ok:true, picked:{txt:picked.txt, cls:picked.cls, rect:picked.rect, score:picked.score, html:picked.html.slice(0,300)}};
}'''

READ = r'''() => ({
  log: (window.__importProbeLog || []).slice(-400),
  fileInputs: Array.from(document.querySelectorAll('input[type=file], input')).map((el, i) => {
    const r = el.getBoundingClientRect();
    return {
      i,
      tag: el.tagName,
      type: el.getAttribute('type') || '',
      accept: el.getAttribute('accept') || '',
      cls: String(el.className || ''),
      id: el.id || '',
      name: el.getAttribute('name') || '',
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: (el.outerHTML || '').slice(0, 220),
    };
  }).slice(0, 100),
  interesting: Array.from(document.querySelectorAll('*')).map(el => {
    const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    const r = el.getBoundingClientRect();
    return {tag:el.tagName,id:el.id||'',cls:String(el.className||''),txt:t.slice(0,160),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:(el.outerHTML || '').slice(0,220)};
  }).filter(x => x.rect.w > 10 && x.rect.h > 10 && /导入文档|Daoruwendang|file|upload|doc|word|drawer|dialog|modal|popover|portal/i.test(x.txt + ' ' + x.id + ' ' + x.cls + ' ' + x.html)).slice(0, 200),
  bodyText: (document.body.innerText || '').slice(0, 6000),
})'''


async def main():
    outdir = base / 'debug' / 'click_importdoc_item_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_click_importdoc_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await context.add_init_script(INIT)
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_function("() => !!document.querySelector('#ueditor_0') && !!document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry, #edui41_state')", timeout=120000)
        await page.wait_for_timeout(8000)
        await page.evaluate(INIT)

        open_result = await page.evaluate(OPEN_MENU)
        await page.wait_for_timeout(1500)
        click_result = await page.evaluate(CLICK_IMPORT)
        await page.wait_for_timeout(6000)
        read1 = await page.evaluate(READ)
        await page.screenshot(path=str(outdir / 'after_click.png'), full_page=True)

        result = {
            'open_result': open_result,
            'click_result': click_result,
            'read': read1,
        }
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'open_ok': open_result.get('ok'),
            'click_ok': click_result.get('ok'),
            'file_inputs': read1.get('fileInputs', []),
            'log_tail_count': len(read1.get('log', [])),
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

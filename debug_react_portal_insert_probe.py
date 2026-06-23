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
  if (window.__portalProbeInstalled) return true;
  window.__portalProbeInstalled = true;
  window.__portalEvents = [];
  const log = (type, data) => { try { window.__portalEvents.push({t:Date.now(), type, data}); } catch (_) {} };
  const desc = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
    return {
      tag: el.tagName || null,
      id: el.id || '',
      cls: String(el.className || ''),
      txt: (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: (el.outerHTML || '').slice(0, 260),
      parentCls: String(el.parentElement?.className || ''),
    };
  };
  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes || []) {
        if (!(node instanceof Element)) continue;
        log('add', desc(node));
        const kids = node.querySelectorAll?.('*') || [];
        kids.forEach(el => {
          const blob = [el.id, el.className, el.innerText || '', el.outerHTML || ''].join(' ');
          if (/导入文档|插入|Daoruwendang|FeEditorApp-|items|portal|dropdown|popover|drawer|popup|file|upload|doc|word/i.test(blob)) {
            log('add:interesting', desc(el));
          }
        });
      }
    }
  });
  mo.observe(document.documentElement || document.body, { childList: true, subtree: true });
  log('installed', {url: location.href});
  return true;
}'''

CLICK_AND_SNAP = r'''() => {
  const out = {};
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
  };
  const entry = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state');
  out.entry = entry ? {txt:textOf(entry), cls:String(entry.className||''), rect:rectOf(entry), html:(entry.outerHTML||'').slice(0, 300)} : null;
  if (entry) {
    const r = entry.getBoundingClientRect();
    const fire = type => entry.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
    ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
    try { if (typeof entry.click === 'function') entry.click(); } catch (_) {}
  }
  out.snapshot = Array.from(document.querySelectorAll('*')).map(el => ({
    tag: el.tagName,
    id: el.id || '',
    cls: String(el.className || ''),
    txt: textOf(el).slice(0, 160),
    rect: rectOf(el),
    html: (el.outerHTML || '').slice(0, 220),
  })).filter(x => x.rect && x.rect.w > 10 && x.rect.h > 10 && /导入文档|插入|Daoruwendang|FeEditorApp-|9d63bce81e3a0b19-item|items|portal|dropdown|popover|drawer|popup/i.test(x.txt + ' ' + x.id + ' ' + x.cls + ' ' + x.html)).slice(0, 150);
  out.fileInputs = Array.from(document.querySelectorAll('input[type=file]')).map(el => ({accept: el.getAttribute('accept') || '', cls: String(el.className || ''), html:(el.outerHTML || '').slice(0, 220)}));
  out.bodyHasImport = (document.body.innerText || '').includes('导入文档');
  return out;
}'''

READ = r'''() => ({
  events: (window.__portalEvents || []).slice(-300),
  snapshot: Array.from(document.querySelectorAll('*')).map(el => {
    const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    const r = el.getBoundingClientRect();
    return {tag:el.tagName,id:el.id||'',cls:String(el.className||''),txt:t.slice(0,160),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:(el.outerHTML||'').slice(0,220)};
  }).filter(x => x.rect.w > 10 && x.rect.h > 10 && /导入文档|插入|Daoruwendang|FeEditorApp-|9d63bce81e3a0b19-item|items|portal|dropdown|popover|drawer|popup|file|upload|doc|word/i.test(x.txt + ' ' + x.id + ' ' + x.cls + ' ' + x.html)).slice(0, 200),
  fileInputs: Array.from(document.querySelectorAll('input[type=file]')).map((el,i) => ({i, accept: el.getAttribute('accept') || '', cls: String(el.className || ''), html:(el.outerHTML || '').slice(0, 220)})),
  bodyText: (document.body.innerText || '').slice(0, 5000),
})'''


async def main():
    outdir = base / 'debug' / 'react_portal_insert_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_react_portal_{int(time.time())}'),
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

        first = await page.evaluate(CLICK_AND_SNAP)
        await page.wait_for_timeout(4000)
        second = await page.evaluate(READ)
        await page.screenshot(path=str(outdir / 'after_click.png'), full_page=True)

        result = {'first': first, 'second': second}
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'entry': first.get('entry'),
            'first_snapshot_count': len(first.get('snapshot', [])),
            'event_count': len(second.get('events', [])),
            'file_inputs': second.get('fileInputs', []),
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

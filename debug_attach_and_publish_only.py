from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from playwright.async_api import async_playwright

PROFILE = base / "edge_profile_cover_open_via_react_1779243941"
URL_PREFIX = "https://baijiahao.baidu.com/builder/rc/edit"

CLICK_PUBLISH = r'''() => {
  const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
  const rows = els.map(el => {
    const t = (el.innerText || el.textContent || '').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    let score = 0;
    if (t === '发布') score += 500;
    if (/发布/.test(t)) score += 180;
    if (cls.includes('primary')) score += 80;
    if (r.y > 650) score += 60;
    return {el, t, cls, score, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 20)
    .sort((a,b) => b.score - a.score || a.rect.y - b.rect.y);
  const picked = rows[0];
  if (!picked) return {ok:false, rows: rows.slice(0,20).map(x => ({t:x.t, cls:x.cls, score:x.score, rect:x.rect}))};
  const r = picked.rect;
  try { picked.el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
  if (typeof picked.el.click === 'function') picked.el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
  }
  return {ok:true, picked:{t:picked.t, cls:picked.cls, score:picked.score, rect:picked.rect}, rows: rows.slice(0,10).map(x => ({t:x.t, cls:x.cls, score:x.score, rect:x.rect}))};
}'''

READ = r'''() => ({
  url: location.href,
  title: document.title,
  bodyText: (document.body.innerText || '').slice(0, 8000),
  dialogs: Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="modal"], [class*="drawer"], [class*="popup"], [class*="popover"]')).map((el, i) => {
    const r = el.getBoundingClientRect();
    return {i, cls:String(el.className||'').slice(0,120), txt:(el.innerText||'').slice(0,300), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
  }).filter(x => x.rect.w > 40 && x.rect.h > 20).slice(0, 20)
})'''

async def main():
    outdir = base / 'debug' / 'attach_publish_only'
    outdir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE),
            channel='msedge',
            headless=False,
            viewport={'width': 1400, 'height': 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        page = None
        for pg in context.pages:
            if pg.url.startswith(URL_PREFIX):
                page = pg
                break
        if page is None:
            page = context.pages[0] if context.pages else await context.new_page()
        await page.bring_to_front()
        await page.wait_for_timeout(1000)

        result = {}
        result['before'] = await page.evaluate(READ)
        result['click_publish'] = await page.evaluate(CLICK_PUBLISH)
        await page.wait_for_timeout(5000)
        result['after'] = await page.evaluate(READ)

        await page.screenshot(path=str(outdir / 'after_click_publish.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await page.wait_for_timeout(600000)

if __name__ == '__main__':
    asyncio.run(main())

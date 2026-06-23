from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

JS = r'''
() => {
  const root=document.querySelector('#ueditor');
  const r=root.getBoundingClientRect();
  const points=[];
  for (const y of [90,110,130,150,170,190,210,230,250]) {
    for (const x of [100,140,180,260,400,700,880]) {
      points.push({x:r.x+(x-84), y:r.y+(y-79)});
    }
  }
  const stacks=points.map(p=>({
    p,
    stack: document.elementsFromPoint(p.x,p.y).slice(0,12).map((el,i)=>({
      i, tag:el.tagName, id:el.id||'', cls:String(el.className||''),
      txt:(el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,120),
      ce:el.getAttribute('contenteditable'), isCE:el.isContentEditable, role:el.getAttribute('role'),
      html:el.outerHTML.slice(0,260)
    }))
  }));
  const all=Array.from(document.querySelectorAll('#ueditor *')).map((el,i)=>{
    const rr=el.getBoundingClientRect();
    return {i, tag:el.tagName, id:el.id||'', cls:String(el.className||''), txt:(el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,120), ce:el.getAttribute('contenteditable'), isCE:el.isContentEditable, role:el.getAttribute('role'), rect:{x:rr.x,y:rr.y,w:rr.width,h:rr.height}, html:el.outerHTML.slice(0,220)};
  }).filter(x => x.rect.w>0 || x.rect.h>0 || x.txt.includes('标题') || x.txt.includes('64'));
  return {root:{x:r.x,y:r.y,w:r.width,h:r.height}, stacks, all: all.slice(0,300)};
}
'''

async def main():
    outdir=base/'debug'/'title_after_click'; outdir.mkdir(parents=True, exist_ok=True)
    cookies=load_cookie_file(base/'ck.txt')
    async with async_playwright() as p:
        context=await p.chromium.launch_persistent_context(str(base/'edge_profile_title_after_click'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context,cookies)
        page=context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(12000)
        info=await page.evaluate(JS)
        (outdir/'stack.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'root': info['root'], 'all_first': info['all'][:80]}, ensure_ascii=False, indent=2))
        await context.close()

if __name__=='__main__': asyncio.run(main())

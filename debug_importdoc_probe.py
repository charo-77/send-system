from __future__ import annotations
import asyncio, json, sys, time
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

JS = r'''
() => {
  const nodes = Array.from(document.querySelectorAll('*'));
  function pack(el, i) {
    const r=el.getBoundingClientRect();
    return {i,tag:el.tagName,id:el.id||'',cls:String(el.className||''),text:(el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,200),title:el.getAttribute('title'),role:el.getAttribute('role'),type:el.getAttribute('type'),accept:el.getAttribute('accept'),name:el.getAttribute('name'),visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:el.outerHTML.slice(0,1000)};
  }
  return nodes.map(pack).filter(x => /importdoc|word|docx|doc|导入|文档|edui-for|upload|file|上传/i.test([x.id,x.cls,x.text,x.title,x.type,x.accept,x.name,x.html].join(' '))).slice(0,2000);
}
'''

CLICK_IMPORTDOC = r'''
() => {
  const candidates = Array.from(document.querySelectorAll('.edui-for-importdoc, [class*=importdoc], [title*=Word], [title*=导入], [title*=文档]'));
  const picked = candidates.map(el => {
    const r=el.getBoundingClientRect();
    return {el,r,txt:(el.innerText||el.textContent||'').trim(),title:el.getAttribute('title'),cls:String(el.className||''),score:(r.width>0&&r.height>0?100:0)+r.y};
  }).sort((a,b)=>b.score-a.score)[0];
  if(!picked) return null;
  const el=picked.el, r=picked.r;
  if (typeof el.click === 'function') el.click();
  for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
  return {tag:el.tagName,id:el.id||'',cls:picked.cls,text:picked.txt,title:picked.title,rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
}
'''

async def main():
    outdir=base/'debug'/'importdoc_probe'; outdir.mkdir(parents=True,exist_ok=True)
    cookies=load_cookie_file(base/'ck.txt')
    async with async_playwright() as p:
        context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_importdoc_probe_{int(time.time())}'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context,cookies)
        page=context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(10000)
        before=await page.evaluate(JS)
        clicked=await page.evaluate(CLICK_IMPORTDOC)
        await page.wait_for_timeout(4000)
        after=await page.evaluate(JS)
        await page.screenshot(path=str(outdir/'after_click_importdoc.png'), full_page=True)
        data={'clicked':clicked,'before':before,'after':after,'url':page.url}
        (outdir/'result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'clicked':clicked,'before_hits':before[:80],'after_hits':after[:120]},ensure_ascii=False,indent=2))
        await context.close()
if __name__=='__main__': asyncio.run(main())

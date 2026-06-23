from __future__ import annotations
import asyncio,json,sys,shutil,time
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from cookies import load_cookie_file
from browser_publish import inject_cookies,DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright
JS=r'''
() => {
 const ids=['ueditor','edui1','edui1_iframeholder','ueditor_0'];
 const byId=ids.map(id=>{const el=document.getElementById(id); if(!el)return {id,missing:true}; const r=el.getBoundingClientRect(); return {id,tag:el.tagName,cls:String(el.className||''),txt:(el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,300),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:el.outerHTML.slice(0,1000)}});
 const ed=document.getElementById('edui1');
 const all=ed?Array.from(ed.querySelectorAll('*')).map((el,i)=>{const r=el.getBoundingClientRect();return {i,tag:el.tagName,id:el.id||'',cls:String(el.className||''),txt:(el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,160),ce:el.getAttribute('contenteditable'),isCE:el.isContentEditable,role:el.getAttribute('role'),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:el.outerHTML.slice(0,300)}}).filter(x=>x.rect.w||x.rect.h||x.txt):[];
 const globals=Object.keys(window).filter(k=>/ue|editor|article|title/i.test(k)).slice(0,200);
 return {url:location.href,ready:document.readyState,byId,all:all.slice(0,300),globals};
}
'''
async def main():
 outdir=base/'debug'/'edui_probe'; outdir.mkdir(parents=True,exist_ok=True)
 cookies=load_cookie_file(base/'ck.txt')
 async with async_playwright() as p:
  context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_edui_probe_{int(time.time())}'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
  await inject_cookies(context,cookies)
  page=context.pages[0] if context.pages else await context.new_page()
  await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
  await page.wait_for_timeout(15000)
  data=await page.evaluate(JS)
  (outdir/'edui.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'byId':data['byId'],'all_first':data['all'][:80],'globals':data['globals'][:50]},ensure_ascii=False,indent=2))
  await context.close()
if __name__=='__main__': asyncio.run(main())

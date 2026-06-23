from __future__ import annotations
import asyncio,json,sys,time
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from articles import extract_docx_article,list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies,DEFAULT_PUBLISH_URLS,fill_article_form,click_visible_text_by_dom
from playwright.async_api import async_playwright
ARTICLE_DIR=Path(r"C:\Users\Administrator\Desktop\mingming\国际")
JS_SNAPSHOT=r'''
() => {
 const nodes=Array.from(document.querySelectorAll('button,[role=button],input,textarea,[contenteditable=true],[class*=cover],[class*=Cover],[class*=upload],[class*=Upload],[class*=img],[class*=Img],[class*=image],[class*=Image],[data-testid],.cheetah-tabs-tab,.cheetah-upload,.bjh-upload'));
 return nodes.map((el,i)=>{const r=el.getBoundingClientRect();return {i,tag:el.tagName,id:el.id||'',cls:String(el.className||''),type:el.getAttribute('type'),accept:el.getAttribute('accept'),testid:el.getAttribute('data-testid'),text:(el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,200),visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:el.outerHTML.slice(0,500)}}).filter(x=>x.visible||x.tag==='INPUT').slice(0,500)
}
'''
async def main():
 outdir=base/'debug'/'cover_probe'; outdir.mkdir(parents=True,exist_ok=True)
 files=list_docx(ARTICLE_DIR); article=extract_docx_article(files[0]); cookies=load_cookie_file(base/'ck.txt')
 async with async_playwright() as p:
  context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_cover_probe_{int(time.time())}'),channel='msedge',headless=False,viewport={'width':1400,'height':900},args=['--disable-blink-features=AutomationControlled'])
  await inject_cookies(context,cookies)
  page=context.pages[0] if context.pages else await context.new_page()
  await page.goto(DEFAULT_PUBLISH_URLS[0],wait_until='domcontentloaded',timeout=60000)
  await page.wait_for_timeout(6000)
  fill=await fill_article_form(page,article)
  await page.wait_for_timeout(1000)
  before=await page.evaluate(JS_SNAPSHOT)
  # Click the underlying Choose Cover entry by DOM, not mouse.
  clicked=await click_visible_text_by_dom(page,'选择封面','button,[role=button],div,span,a')
  await page.wait_for_timeout(4000)
  after=await page.evaluate(JS_SNAPSHOT)
  await page.screenshot(path=str(outdir/'after_choose_cover.png'),full_page=True)
  data={'fill':fill,'clicked':clicked,'before':before,'after':after,'url':page.url}
  (outdir/'cover_probe.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'clicked':clicked,'after_interesting':[x for x in after if any(k in (x.get('text','')+x.get('cls','')+x.get('html','')) for k in ['上传','选择','封面','图片','本地','正文','input','upload','cover'])][:120]},ensure_ascii=False,indent=2))
  await context.close()
if __name__=='__main__': asyncio.run(main())

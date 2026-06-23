from __future__ import annotations
import asyncio,json,sys,time
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from cookies import load_cookie_file
from browser_publish import inject_cookies,DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright
JS=r'''
() => {
 const uiName='$'+'EDITORUI_V2';
 const safeKeys=o=>{try{return o?Object.keys(o).slice(0,200):null}catch(e){return String(e)}};
 const instants=window.UE_V2?.instants;
 const instKeys=safeKeys(instants);
 const inst=instants && Object.values(instants)[0];
 return {
  href: location.href,
  ready: document.readyState,
  globals: Object.keys(window).filter(k=>/UE|editor|edui|ueditor/i.test(k)).slice(0,100),
  UE_type: typeof window.UE,
  UE_V2_type: typeof window.UE_V2,
  UI_type: typeof window[uiName],
  instKeys,
  instExists: !!inst,
  instKey: instants ? Object.keys(instants)[0] : null,
  instKeys2: safeKeys(inst),
  hasExec: typeof inst?.execCommand,
  hasSetContent: typeof inst?.setContent,
  hasGetContent: typeof inst?.getContent,
  bodyText: inst?.body?.innerText?.slice(0,100),
  bodyHTML: inst?.body?.innerHTML?.slice(0,200),
  docBodyText: document.body?.innerText?.slice(0,200),
 };
}
'''
async def main():
 outdir=base/'debug'/'frame_editor_probe'; outdir.mkdir(parents=True,exist_ok=True)
 cookies=load_cookie_file(base/'ck.txt')
 async with async_playwright() as p:
  context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_frame_editor_{int(time.time())}'),channel='msedge',headless=False,viewport={'width':1400,'height':900},args=['--disable-blink-features=AutomationControlled'])
  await inject_cookies(context,cookies)
  page=context.pages[0] if context.pages else await context.new_page()
  await page.goto(DEFAULT_PUBLISH_URLS[0],wait_until='domcontentloaded',timeout=60000)
  await page.wait_for_timeout(12000)
  # click body once to initialize selection/editor state
  try:
   fe=await page.wait_for_selector('iframe#ueditor_0', timeout=10000)
   fr=await fe.content_frame()
   await fr.locator('body').first.click(force=True)
   await page.wait_for_timeout(1000)
  except Exception:
   pass
  rows=[]
  for fr in page.frames:
   try:
    rows.append(await fr.evaluate(JS))
   except Exception as e:
    rows.append({'href':fr.url,'error':str(e)[:300]})
  (outdir/'result.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(rows,ensure_ascii=False,indent=2))
  await context.close()
if __name__=='__main__': asyncio.run(main())

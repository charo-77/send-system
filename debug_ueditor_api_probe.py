from __future__ import annotations
import asyncio,json,sys,time
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from articles import extract_docx_article,list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies,DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright
ARTICLE_DIR=Path(r"C:\Users\Administrator\Desktop\mingming\国际")
JS=r'''
() => {
  const out = {
    globals: Object.keys(window).filter(k => /UE|ueditor|editor|Editor/.test(k)).slice(0,500),
    ueType: typeof window.UE,
    ueditorType: typeof window.ueditor,
    editorType: typeof window.editor,
    baiduType: typeof window.baidu,
  };
  try {
    out.UEKeys = window.UE ? Object.keys(window.UE).slice(0,200) : null;
    out.hasGetEditor = !!(window.UE && window.UE.getEditor);
  } catch(e) { out.UEErr = String(e); }
  try {
    const ed = window.UE && window.UE.getEditor ? window.UE.getEditor('ueditor') : null;
    out.edExists = !!ed;
    if (ed) {
      out.edKeys = Object.keys(ed).slice(0,200);
      out.hasSetContent = typeof ed.setContent;
      out.hasGetContent = typeof ed.getContent;
      out.hasReady = typeof ed.ready;
      out.isReady = ed.isReady;
      out.bodyText = ed.body ? ed.body.innerText.slice(0,200) : null;
      out.content = ed.getContent ? ed.getContent().slice(0,200) : null;
    }
  } catch(e) { out.edErr = String(e); }
  return out;
}
'''
async def main():
 outdir=base/'debug'/'ueditor_api_probe'; outdir.mkdir(parents=True,exist_ok=True)
 article=extract_docx_article(list_docx(ARTICLE_DIR)[0]); cookies=load_cookie_file(base/'ck.txt')
 async with async_playwright() as p:
  context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_ueditor_probe_{int(time.time())}'),channel='msedge',headless=False,viewport={'width':1400,'height':900},args=['--disable-blink-features=AutomationControlled'])
  await inject_cookies(context,cookies)
  page=context.pages[0] if context.pages else await context.new_page()
  await page.goto(DEFAULT_PUBLISH_URLS[0],wait_until='domcontentloaded',timeout=60000)
  await page.wait_for_timeout(8000)
  data=await page.evaluate(JS)
  (outdir/'ueditor_api.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(data,ensure_ascii=False,indent=2))
  await context.close()
if __name__=='__main__': asyncio.run(main())

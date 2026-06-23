from __future__ import annotations
import asyncio,json,re,sys,time,urllib.request
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from cookies import load_cookie_file
from browser_publish import inject_cookies,DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright
async def main():
 outdir=base/'debug'/'all_scripts'; outdir.mkdir(parents=True,exist_ok=True)
 cookies=load_cookie_file(base/'ck.txt')
 async with async_playwright() as p:
  context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_scripts_{int(time.time())}'),channel='msedge',headless=False,viewport={'width':1400,'height':900},args=['--disable-blink-features=AutomationControlled'])
  await inject_cookies(context,cookies)
  page=context.pages[0] if context.pages else await context.new_page()
  await page.goto(DEFAULT_PUBLISH_URLS[0],wait_until='networkidle',timeout=120000)
  await page.wait_for_timeout(12000)
  urls=await page.evaluate("""() => Array.from(document.scripts).map(s=>s.src).filter(Boolean)""")
  (outdir/'urls.json').write_text(json.dumps(urls,ensure_ascii=False,indent=2),encoding='utf-8')
  print('script urls', len(urls))
  await context.close()
 for u in urls:
  name=re.sub(r'[^A-Za-z0-9_.-]+','_',u)[-180:]
  fp=outdir/name
  if not fp.exists():
   try:
    fp.write_bytes(urllib.request.urlopen(u,timeout=40).read())
    print('fetched', name, fp.stat().st_size)
   except Exception as e:
    print('fetch fail',u,e)
 for fp in outdir.iterdir():
  if not fp.is_file() or fp.suffix.lower() not in ['.js',''] and '.js' not in fp.name: continue
  s=fp.read_text(encoding='utf-8',errors='ignore')
  if re.search('importdoc|consumerIsWordDocument|filterWord|showWordImageDialog|wordimage|docx|导入|文档',s,re.I):
   print('\nMATCH',fp.name,len(s))
   for pat in ['importdoc','consumerIsWordDocument','filterWord','showWordImageDialog','wordimage','docx','导入','文档']:
    m=re.search(pat,s,re.I)
    if m:
     a=max(0,m.start()-1500); b=min(len(s),m.end()+5000)
     print('PAT',pat,s[a:b][:6500])
     break
if __name__=='__main__': asyncio.run(main())

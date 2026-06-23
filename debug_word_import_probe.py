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
    const r = el.getBoundingClientRect();
    return {
      i, tag: el.tagName, id: el.id || '', cls: String(el.className || ''),
      text: (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g,' ').slice(0,300),
      title: el.getAttribute('title'), aria: el.getAttribute('aria-label'), role: el.getAttribute('role'),
      type: el.getAttribute('type'), accept: el.getAttribute('accept'), name: el.getAttribute('name'),
      testid: el.getAttribute('data-testid'), visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0,800)
    }
  }
  const keywords = /word|docx|doc|文档|导入|一键填写|上传|文件|素材|插入/i;
  return nodes.map(pack).filter(x => keywords.test([x.text,x.cls,x.id,x.title,x.aria,x.role,x.type,x.accept,x.name,x.testid,x.html].join(' '))).slice(0,1000);
}
'''

async def main():
    outdir=base/'debug'/'word_import_probe'; outdir.mkdir(parents=True,exist_ok=True)
    cookies=load_cookie_file(base/'ck.txt')
    async with async_playwright() as p:
        context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_word_import_probe_{int(time.time())}'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context,cookies)
        page=context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(8000)
        before=await page.evaluate(JS)
        # Try opening likely menus without depending on tour overlay.
        clicks=[]
        for text in ['插入', '一键填写']:
            try:
                res=await page.evaluate('''text => {
                    const els=Array.from(document.querySelectorAll('button,[role=button],div,span,a')).filter(el => (el.innerText||el.textContent||'').trim()===text);
                    const el=els.find(el => {const r=el.getBoundingClientRect(); return r.width>0&&r.height>0&&r.x>=0&&r.y>=0}) || els[0];
                    if(!el) return null;
                    const r=el.getBoundingClientRect();
                    if (typeof el.click === 'function') el.click();
                    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
                    return {text, tag:el.tagName, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                }''', text)
                clicks.append(res)
                await page.wait_for_timeout(1500)
            except Exception as e:
                clicks.append({'text':text,'error':str(e)[:300]})
        after=await page.evaluate(JS)
        await page.screenshot(path=str(outdir/'after_probe.png'), full_page=True)
        data={'clicks':clicks,'before':before,'after':after,'url':page.url}
        (outdir/'result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'clicks':clicks,'interesting_after':after[:120]},ensure_ascii=False,indent=2))
        await context.close()
if __name__=='__main__': asyncio.run(main())

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / "ck.txt"
URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"

JS_DEEP = r'''() => {
  const nodes = Array.from(document.querySelectorAll('*'));
  const rows = nodes.map((el, i) => {
    const r = el.getBoundingClientRect();
    return {
      i,
      tag: el.tagName,
      id: el.id || '',
      cls: String(el.className || ''),
      text: (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 300),
      title: el.getAttribute('title'),
      role: el.getAttribute('role'),
      type: el.getAttribute('type'),
      accept: el.getAttribute('accept'),
      name: el.getAttribute('name'),
      testid: el.getAttribute('data-testid'),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: el.outerHTML.slice(0, 1000),
    };
  });
  const interesting = rows.filter(x => /导入文档|插入|word|docx|doc|upload|file|dialog|modal|drawer|accept=|iframe|导入|文档/i.test([x.id,x.cls,x.text,x.title,x.role,x.type,x.accept,x.name,x.testid,x.html].join(' '))).slice(0, 2000);
  const iframes = Array.from(document.querySelectorAll('iframe')).map((el,i) => {
    const r = el.getBoundingClientRect();
    return {i, id:el.id||'', cls:String(el.className||''), name:el.name||'', src:el.src||'', visible:!!(el.offsetWidth || el.offsetHeight || el.getClientRects().length), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:el.outerHTML.slice(0,300)};
  });
  const files = Array.from(document.querySelectorAll('input[type=file]')).map((el,i)=>({i,id:el.id||'',cls:String(el.className||''),accept:el.getAttribute('accept'),name:el.getAttribute('name'),visible:!!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),html:el.outerHTML.slice(0,500)}));
  return {interesting, iframes, files, body:(document.body.innerText||'').slice(0,6000)};
}'''

async def click_exact(page, text: str):
    return await page.evaluate(r'''text => {
      const hits = Array.from(document.querySelectorAll('*')).map(el => {
        const t = (el.innerText || el.textContent || '').trim();
        const r = el.getBoundingClientRect();
        return {el, t, r, cls: String(el.className || ''), id: el.id || ''};
      }).filter(x => x.t === text && x.r.width > 5 && x.r.height > 5 && x.r.x >= 0 && x.r.y >= 0)
        .sort((a,b) => b.r.y - a.r.y || a.r.x - b.r.x);
      const x = hits[0];
      if (!x) return null;
      const rr = x.r;
      x.el.scrollIntoView({block:'center'});
      for (const type of ['pointerover','mouseover','mouseenter','pointermove','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
        x.el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:rr.x+rr.width/2,clientY:rr.y+rr.height/2,button:0}));
      }
      if (typeof x.el.click === 'function') x.el.click();
      return {text:x.t, id:x.id, cls:x.cls, rect:{x:rr.x,y:rr.y,w:rr.width,h:rr.height}};
    }''', text)

async def main():
    outdir = base / "debug" / "importdoc_deep_after_click"
    outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_importdoc_deep_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        # close tour if present
        closed = []
        for txt in ["下一步", "我知道了", "我知道了"]:
            try:
                r = await click_exact(page, txt)
                if r:
                    closed.append(r)
                    await page.wait_for_timeout(1200)
            except Exception:
                pass

        # real hover insert
        insert = page.locator('#edui41_state, #edui41, .edui-for-bjhInsertionDrawer').first
        box = await insert.bounding_box()
        if box:
            await page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=25)
            await page.wait_for_timeout(2000)

        before_click = await page.evaluate(JS_DEEP)
        import_doc = await click_exact(page, '导入文档')
        await page.wait_for_timeout(1000)
        after_1s = await page.evaluate(JS_DEEP)
        await page.wait_for_timeout(3000)
        after_4s = await page.evaluate(JS_DEEP)
        await page.wait_for_timeout(6000)
        after_10s = await page.evaluate(JS_DEEP)

        # read accessible frame contents too
        frame_dump = []
        for fr in page.frames:
            try:
                txt = await fr.locator('body').inner_text(timeout=1000)
                frame_dump.append({'url': fr.url, 'text': txt[:2000]})
            except Exception as e:
                frame_dump.append({'url': fr.url, 'error': str(e)[:300]})

        await page.screenshot(path=str(outdir / 'after.png'), full_page=True)
        data = {
            'url': page.url,
            'closed': closed,
            'insert_box': box,
            'import_doc': import_doc,
            'before_click': before_click,
            'after_1s': after_1s,
            'after_4s': after_4s,
            'after_10s': after_10s,
            'frames': frame_dump,
        }
        (outdir / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

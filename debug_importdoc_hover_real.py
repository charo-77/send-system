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
DOCX_DIR = Path(r"C:\Users\Administrator\Desktop\mingming\国际")

JS_FIND = r'''kw => {
  const nodes = Array.from(document.querySelectorAll('*'));
  return nodes.map((el, i) => {
    const r = el.getBoundingClientRect();
    return {
      i, tag: el.tagName, id: el.id || '', cls: String(el.className || ''),
      text: (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 200),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height}, html: el.outerHTML.slice(0, 500)
    };
  }).filter(x => x.visible && [x.text,x.id,x.cls,x.html].join(' ').includes(kw)).slice(0, 200)
}'''

async def click_text(page, text: str):
    return await page.evaluate(r'''text => {
      const hits = Array.from(document.querySelectorAll('*')).map(el => {
        const t = (el.innerText || el.textContent || '').trim();
        const r = el.getBoundingClientRect();
        return {el, t, r, cls: String(el.className || ''), id: el.id || ''};
      }).filter(x => x.t === text && x.r.width > 5 && x.r.height > 5 && x.r.x >= 0 && x.r.y >= 0)
        .sort((a,b) => b.r.y - a.r.y || a.r.x - b.r.x);
      const x = hits[0];
      if (!x) return null;
      x.el.scrollIntoView({block:'center'});
      const rr = x.el.getBoundingClientRect();
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        x.el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:rr.x+rr.width/2,clientY:rr.y+rr.height/2,button:0}));
      }
      if (typeof x.el.click === 'function') x.el.click();
      return {text:x.t, id:x.id, cls:x.cls, rect:{x:rr.x,y:rr.y,w:rr.width,h:rr.height}};
    }''', text)

async def main():
    outdir = base / "debug" / "importdoc_hover_real"
    outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookie_file(CK)
    docx = sorted(DOCX_DIR.glob("*.docx"))[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_importdoc_hover_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        injected = await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        # Kill tour overlay first.
        closed = []
        for txt in ["我知道了", "下一步", "我知道了"]:
            try:
                r = await click_text(page, txt)
                if r:
                    closed.append(r)
                    await page.wait_for_timeout(1200)
            except Exception:
                pass

        # Real mouse hover on insert area.
        insert = page.locator('#edui41_state, #edui41, .edui-for-bjhInsertionDrawer').first
        box = await insert.bounding_box()
        hover_box = None
        if box:
            hover_box = box
            await page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2, steps=20)
            await page.wait_for_timeout(1200)
            await page.mouse.move(box['x'] + box['width']/2 + 2, box['y'] + box['height']/2 + 2, steps=5)
            await page.wait_for_timeout(1800)

        # Snapshot after real hover.
        import_hits = await page.evaluate(JS_FIND, '导入文档')
        insert_hits = await page.evaluate(JS_FIND, '插入')

        import_click = None
        if import_hits:
            h = import_hits[0]
            await page.mouse.move(h['rect']['x'] + h['rect']['w']/2, h['rect']['y'] + h['rect']['h']/2, steps=15)
            await page.wait_for_timeout(300)
            await page.mouse.click(h['rect']['x'] + h['rect']['w']/2, h['rect']['y'] + h['rect']['h']/2)
            await page.wait_for_timeout(3000)
            import_click = h

        file_inputs = await page.evaluate(r'''() => Array.from(document.querySelectorAll('input[type=file]')).map((el,i)=>({
          i, id:el.id||'', cls:String(el.className||''), accept:el.getAttribute('accept'), name:el.getAttribute('name'),
          hidden: !(el.offsetWidth || el.offsetHeight || el.getClientRects().length), html: el.outerHTML.slice(0,500)
        }))''')

        upload_result = None
        picked = None
        try:
            selectors = [
                'input[type="file"][accept*="doc"]',
                'input[type="file"][accept*="word"]',
                'input[type="file"]:not([accept*="video"])',
            ]
            for sel in selectors:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    picked = sel
                    await loc.last.set_input_files(str(docx))
                    await page.wait_for_timeout(15000)
                    upload_result = {"uploaded": True, "selector": sel, "docx": str(docx)}
                    break
            if upload_result is None:
                upload_result = {"uploaded": False, "error": "no doc-style input after hover"}
        except Exception as e:
            upload_result = {"uploaded": False, "selector": picked, "error": str(e)}

        body_text = await page.locator('body').inner_text(timeout=3000)
        await page.screenshot(path=str(outdir / 'after.png'), full_page=True)
        data = {
            'url': page.url,
            'cookies_injected': injected,
            'closed_tour': closed,
            'hover_box': hover_box,
            'insert_hits': insert_hits,
            'import_hits': import_hits,
            'import_click': import_click,
            'file_inputs': file_inputs,
            'upload_result': upload_result,
            'body_prefix': body_text[:6000],
        }
        (outdir / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

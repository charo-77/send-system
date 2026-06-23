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

JS_IMPORT_STATE = r'''() => {
  const nodes = Array.from(document.querySelectorAll('*'));
  return nodes.map((el, i) => {
    const r = el.getBoundingClientRect();
    return {
      i,
      tag: el.tagName,
      id: el.id || '',
      cls: String(el.className || ''),
      text: (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 200),
      title: el.getAttribute('title'),
      type: el.getAttribute('type'),
      accept: el.getAttribute('accept'),
      name: el.getAttribute('name'),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: el.outerHTML.slice(0, 800),
    };
  }).filter(x => /插入|导入文档|文档|word|docx|video\/*|bjhInsertionDrawer|edui41|file|upload|accept=/i.test([x.id,x.cls,x.text,x.title,x.type,x.accept,x.name,x.html].join(' '))).slice(0, 1000)
}'''

async def open_insert_menu(page):
    return await page.evaluate(r'''() => {
      const candidates = [
        document.querySelector('#edui41_state'),
        document.querySelector('#edui41'),
        document.querySelector('.edui-for-bjhInsertionDrawer'),
        document.querySelector('[id*=edui41]'),
      ].filter(Boolean);
      if (!candidates.length) return null;
      const el = candidates[0];
      const r = el.getBoundingClientRect();
      const out = {tag: el.tagName, id: el.id || '', cls: String(el.className || ''), text: (el.innerText || el.textContent || '').trim(), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
      for (const type of ['pointerover','mouseover','mouseenter','pointermove','mousemove']) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2}));
      }
      for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
      if (typeof el.click === 'function') el.click();
      return out;
    }''')

async def find_and_click_import_doc(page):
    return await page.evaluate(r'''() => {
      const all = Array.from(document.querySelectorAll('*')).map(el => {
        const t = (el.innerText || el.textContent || '').trim();
        const r = el.getBoundingClientRect();
        return {el, t, r, cls: String(el.className || ''), id: el.id || '', html: el.outerHTML || ''};
      });
      const hits = all.filter(x => x.t === '导入文档' && x.r.width > 5 && x.r.height > 5 && x.r.x >= 0 && x.r.y >= 0)
        .sort((a,b) => b.r.y - a.r.y || a.r.x - b.r.x);
      const x = hits[0];
      if (!x) return {found: false, candidates: all.filter(x => /导入文档|插入/.test(x.t)).map(x => ({t:x.t,id:x.id,cls:x.cls,rect:{x:x.r.x,y:x.r.y,w:x.r.width,h:x.r.height}})).slice(0,50)};
      const el = x.el;
      for (const type of ['pointerover','mouseover','mouseenter','pointermove','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:x.r.x+x.r.width/2,clientY:x.r.y+x.r.height/2,button:0}));
      }
      if (typeof el.click === 'function') el.click();
      return {found: true, text:x.t, id:x.id, cls:x.cls, rect:{x:x.r.x,y:x.r.y,w:x.r.width,h:x.r.height}};
    }''')

async def main():
    outdir = base / "debug" / "importdoc_only"
    outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookie_file(CK)
    docx = sorted(DOCX_DIR.glob("*.docx"))[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_importdoc_only_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        injected = await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        s0 = await page.evaluate(JS_IMPORT_STATE)
        insert = await open_insert_menu(page)
        await page.wait_for_timeout(2500)
        s1 = await page.evaluate(JS_IMPORT_STATE)
        import_doc = await find_and_click_import_doc(page)
        await page.wait_for_timeout(4000)
        s2 = await page.evaluate(JS_IMPORT_STATE)

        file_inputs = await page.evaluate(r'''() => Array.from(document.querySelectorAll('input[type=file]')).map((el,i)=>({
          i, id:el.id||'', cls:String(el.className||''), accept:el.getAttribute('accept'), name:el.getAttribute('name'), hidden: !(el.offsetWidth || el.offsetHeight || el.getClientRects().length), html: el.outerHTML.slice(0,500)
        }))''')

        picked_input = None
        upload_result = None
        try:
            candidates = [
                'input[type="file"][accept*="doc"]',
                'input[type="file"][accept*="word"]',
                'input[type="file"][accept*="application"]',
                'input[type="file"]:not([accept*="video"])',
            ]
            for sel in candidates:
                loc = page.locator(sel)
                if await loc.count() > 0:
                    picked_input = sel
                    await loc.last.set_input_files(str(docx))
                    await page.wait_for_timeout(15000)
                    upload_result = {"uploaded": True, "selector": sel, "docx": str(docx)}
                    break
            if upload_result is None:
                upload_result = {"uploaded": False, "error": "no non-video doc input found"}
        except Exception as e:
            upload_result = {"uploaded": False, "selector": picked_input, "error": str(e)}

        s3 = await page.evaluate(JS_IMPORT_STATE)
        body_text = await page.locator('body').inner_text(timeout=3000)
        await page.screenshot(path=str(outdir / 'after.png'), full_page=True)
        data = {
            'url': page.url,
            'cookies_injected': injected,
            'insert': insert,
            'import_doc': import_doc,
            'file_inputs': file_inputs,
            'picked_input': picked_input,
            'upload_result': upload_result,
            's0': s0,
            's1': s1,
            's2': s2,
            's3': s3,
            'body_prefix': body_text[:5000],
        }
        (outdir / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

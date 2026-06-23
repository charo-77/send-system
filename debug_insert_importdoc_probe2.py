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

SNAP = r'''() => {
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
  }).filter(x => /插入|导入文档|文档|word|docx|file|upload|bjhInsertionDrawer|edui41/i.test([x.id,x.cls,x.text,x.title,x.type,x.accept,x.name,x.html].join(' '))).slice(0, 800)
}'''

async def trigger_insert_drawer(page):
    return await page.evaluate(r'''() => {
      const el = document.querySelector('#edui41_state, #edui41, .edui-for-bjhInsertionDrawer, .FeEditorApp-_4ecaee52b311664f-entry');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const detail = {tag: el.tagName, id: el.id || '', cls: String(el.className || ''), text: (el.innerText || el.textContent || '').trim(), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
      for (const type of ['pointerover','mouseover','mouseenter','pointermove','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
      if (typeof el.click === 'function') el.click();
      return detail;
    }''')

async def click_import_doc(page):
    return await page.evaluate(r'''() => {
      const els = Array.from(document.querySelectorAll('*')).map(el => {
        const t = (el.innerText || el.textContent || '').trim();
        const r = el.getBoundingClientRect();
        return {el, t, r, cls: String(el.className || ''), id: el.id || ''};
      }).filter(x => x.t === '导入文档' && x.r.width > 5 && x.r.height > 5 && x.r.x >= 0 && x.r.y >= 0)
        .sort((a,b) => b.r.y - a.r.y || a.r.x - b.r.x);
      const x = els[0];
      if (!x) return null;
      const el = x.el;
      for (const type of ['pointerover','mouseover','mouseenter','pointerdown','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:x.r.x+x.r.width/2,clientY:x.r.y+x.r.height/2,button:0}));
      }
      if (typeof el.click === 'function') el.click();
      return {text:x.t, cls:x.cls, id:x.id, rect:{x:x.r.x,y:x.r.y,w:x.r.width,h:x.r.height}};
    }''')

async def main():
    outdir = base / "debug" / "insert_importdoc_probe2"
    outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookie_file(CK)
    docx = sorted(DOCX_DIR.glob("*.docx"))[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_importdoc_menu2_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        injected = await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        before = await page.evaluate(SNAP)
        insert = await trigger_insert_drawer(page)
        await page.wait_for_timeout(2500)
        after_insert = await page.evaluate(SNAP)
        import_doc = await click_import_doc(page)
        await page.wait_for_timeout(3000)
        after_import_click = await page.evaluate(SNAP)

        inputs = await page.evaluate(r'''() => Array.from(document.querySelectorAll('input[type=file]')).map((el,i)=>({
          i, id:el.id||'', cls:String(el.className||''), accept:el.getAttribute('accept'), name:el.getAttribute('name'),
          hidden: !(el.offsetWidth || el.offsetHeight || el.getClientRects().length), html: el.outerHTML.slice(0,400)
        }))''')

        upload_result = None
        try:
            # Prefer doc/docx-capable input if it appears; fallback to last file input.
            locator = page.locator('input[type="file"][accept*="doc"], input[type="file"][accept*="word"], input[type="file"]').last
            await locator.set_input_files(str(docx))
            await page.wait_for_timeout(12000)
            upload_result = {"uploaded": True, "docx": str(docx)}
        except Exception as e:
            upload_result = {"uploaded": False, "error": str(e)}

        body_text = await page.locator("body").inner_text(timeout=3000)
        final = await page.evaluate(SNAP)
        await page.screenshot(path=str(outdir / "after.png"), full_page=True)
        data = {
            "url": page.url,
            "cookies_injected": injected,
            "insert": insert,
            "import_doc": import_doc,
            "before": before,
            "after_insert": after_insert,
            "after_import_click": after_import_click,
            "file_inputs": inputs,
            "upload_result": upload_result,
            "final": final,
            "body_prefix": body_text[:5000],
        }
        (outdir / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

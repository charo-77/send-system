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

JS_SNAPSHOT = r'''() => {
  const nodes = Array.from(document.querySelectorAll('button,[role=button],a,div,span,input'));
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
      html: el.outerHTML.slice(0, 500),
    };
  }).filter(x => /插入|导入|文档|word|docx|upload|file/i.test([x.text,x.id,x.cls,x.title,x.type,x.accept,x.name,x.html].join(' '))).slice(0, 500)
}'''

async def click_by_text(page, text: str):
    return await page.evaluate(r'''text => {
      const els = Array.from(document.querySelectorAll('button,[role=button],a,div,span'));
      const pick = els.map(el => {
        const t = (el.innerText || el.textContent || '').trim();
        const r = el.getBoundingClientRect();
        return {el, t, r, cls: String(el.className || '')};
      }).filter(x => x.t === text && x.r.width > 5 && x.r.height > 5 && x.r.x >= 0 && x.r.y >= 0)
        .sort((a,b) => a.r.y - b.r.y || a.r.x - b.r.x)[0];
      if (!pick) return null;
      const el = pick.el;
      if (typeof el.click === 'function') el.click();
      for (const type of ['pointerdown','mouseover','mouseenter','mousedown','pointerup','mouseup','click']) {
        el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:pick.r.x + pick.r.width/2,clientY:pick.r.y + pick.r.height/2,button:0}));
      }
      return {text:pick.t, cls:pick.cls, rect:{x:pick.r.x,y:pick.r.y,w:pick.r.width,h:pick.r.height}};
    }''', text)

async def main():
    outdir = base / "debug" / "insert_importdoc_probe"
    outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookie_file(CK)
    docx = sorted(DOCX_DIR.glob("*.docx"))[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f"edge_profile_importdoc_menu_{int(time.time())}"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        injected = await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)

        before = await page.evaluate(JS_SNAPSHOT)
        hover_insert = await click_by_text(page, "插入")
        await page.wait_for_timeout(1500)
        after_hover = await page.evaluate(JS_SNAPSHOT)
        click_import = await click_by_text(page, "导入文档")
        await page.wait_for_timeout(3000)
        after_click = await page.evaluate(JS_SNAPSHOT)

        inputs = await page.evaluate(r'''() => Array.from(document.querySelectorAll('input[type=file]')).map((el,i)=>({
          i, id:el.id||'', cls:String(el.className||''), accept:el.getAttribute('accept'), name:el.getAttribute('name'),
          hidden: !(el.offsetWidth || el.offsetHeight || el.getClientRects().length), html: el.outerHTML.slice(0,300)
        }))''')

        upload_result = None
        try:
            file_input = page.locator('input[type="file"]').last
            await file_input.set_input_files(str(docx))
            await page.wait_for_timeout(8000)
            upload_result = {"uploaded": True, "docx": str(docx)}
        except Exception as e:
            upload_result = {"uploaded": False, "error": str(e)}

        final_state = await page.evaluate(JS_SNAPSHOT)
        url = page.url
        body_text = await page.locator("body").inner_text(timeout=3000)
        await page.screenshot(path=str(outdir / "after.png"), full_page=True)
        data = {
            "url": url,
            "cookies_injected": injected,
            "hover_insert": hover_insert,
            "click_import": click_import,
            "before": before,
            "after_hover": after_hover,
            "after_click": after_click,
            "file_inputs": inputs,
            "upload_result": upload_result,
            "final_state": final_state,
            "body_prefix": body_text[:4000],
        }
        (outdir / "result.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

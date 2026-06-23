from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / "ck.txt"
URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"

JS_DUMP = r'''() => {
  const UI = window['$' + 'EDITORUI_V2'] || null;
  const instants = window.UE_V2?.instants || {};
  const inst = instants.ueditorInstant0 || null;
  const ed41 = UI?.edui41 || null;
  const ed42 = UI?.edui42 || null;
  const pick = (obj) => {
    if (!obj) return null;
    const own = Object.keys(obj);
    const proto = Object.getPrototypeOf(obj);
    const protoKeys = proto ? Object.getOwnPropertyNames(proto) : [];
    return {
      ownKeys: own.slice(0, 300),
      protoKeys: protoKeys.slice(0, 300),
      matchedOwn: own.filter(k => /show|popup|menu|item|render|attach|import|doc|word|drawer|upload|dialog|exec|click|hover/i.test(k)).slice(0, 200),
      matchedProto: protoKeys.filter(k => /show|popup|menu|item|render|attach|import|doc|word|drawer|upload|dialog|exec|click|hover/i.test(k)).slice(0, 200),
    };
  };
  return {
    ready: {
      hasUI: !!UI,
      hasUEV2: !!window.UE_V2,
      instantKeys: Object.keys(instants).slice(0, 50),
      hasInst: !!inst,
      hasEd41: !!ed41,
      hasEd42: !!ed42,
      bodyHasImport: document.body.innerText.includes('导入文档'),
    },
    ed41: pick(ed41),
    ed42: pick(ed42),
    inst: inst ? {
      ownKeys: Object.keys(inst).slice(0, 300),
      commandNames: inst.commands ? Object.keys(inst.commands).slice(0, 300) : [],
      matchedCommands: inst.commands ? Object.keys(inst.commands).filter(k => /import|doc|word|insert|drawer|upload|dialog/i.test(k)).slice(0, 100) : [],
    } : null,
    importNodes: Array.from(document.querySelectorAll('*')).map(el => {
      const txt = (el.innerText || el.textContent || '').trim();
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName, id: el.id || '', cls: String(el.className || ''), txt: txt.slice(0, 100),
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
        rect: {x:r.x,y:r.y,w:r.width,h:r.height},
        html: el.outerHTML.slice(0, 300)
      };
    }).filter(x => /导入文档|插入|edui41|edui42|bjhInsertionDrawer/i.test([x.id,x.cls,x.txt,x.html].join(' '))).slice(0, 100)
  };
}'''

JS_TRY = r'''() => {
  const out = { attempts: [] };
  const UI = window['$' + 'EDITORUI_V2'] || null;
  const ed41 = UI?.edui41 || null;
  const state = document.querySelector('#edui41_state');
  const popup = () => document.querySelector('#edui42');
  const content = () => document.querySelector('#edui42_content');
  const snap = (label) => {
    const p = popup();
    const c = content();
    const pr = p ? p.getBoundingClientRect() : null;
    const cr = c ? c.getBoundingClientRect() : null;
    out.attempts.push({
      label,
      popup: p ? {style:p.getAttribute('style'), cls:p.className, rect: pr && {x:pr.x,y:pr.y,w:pr.width,h:pr.height}} : null,
      content: c ? {html:(c.innerHTML || '').slice(0, 1000), text:(c.innerText || '').slice(0, 300), childCount:c.children.length, rect: cr && {x:cr.x,y:cr.y,w:cr.width,h:cr.height}} : null,
      bodyHasImport: document.body.innerText.includes('导入文档')
    });
  };

  snap('before');

  try {
    if (state) {
      const r = state.getBoundingClientRect();
      for (const type of ['mouseover','mouseenter','mousemove','pointerover','pointerenter','pointermove']) {
        state.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
      }
      snap('after-state-hover-events');
    }
  } catch (e) { out.hoverErr = String(e); }

  try {
    if (ed41) {
      const proto = Object.getPrototypeOf(ed41);
      const methods = proto ? Object.getOwnPropertyNames(proto).filter(k => /show|popup|menu|render|attach|hover|over|mouse/i.test(k)) : [];
      out.ed41Methods = methods;
      for (const name of methods) {
        if (typeof ed41[name] === 'function' && /show|popup|render|over/i.test(name)) {
          try {
            ed41[name]({type:'mouseover', button:0, target:state}, state);
            snap('after-ed41-' + name);
          } catch (e) {
            out.attempts.push({label:'err-' + name, error:String(e)});
          }
        }
      }
    }
  } catch (e) { out.ed41Err = String(e); }

  try {
    const p = popup();
    if (p) {
      p.style.display = 'block';
      const c = content();
      if (c) c.style.display = 'block';
      snap('after-force-display');
    }
  } catch (e) { out.forceErr = String(e); }

  out.fileInputs = Array.from(document.querySelectorAll('input[type=file]')).map((el,i)=>({
    i, accept: el.getAttribute('accept'), name: el.getAttribute('name'), id: el.id || '', cls: String(el.className || ''),
    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
    html: el.outerHTML.slice(0, 300)
  }));

  return out;
}'''

async def main():
    outdir = base / 'debug' / 'internal_entry_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_internal_probe_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1400, 'height': 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)

        await page.wait_for_function(
            """() => !!document.querySelector('#edui41_state') && !!document.querySelector('#ueditor_0') && !!window['$' + 'EDITORUI_V2']""",
            timeout=120000,
        )
        await page.wait_for_timeout(8000)

        dump1 = await page.evaluate(JS_DUMP)
        tried = await page.evaluate(JS_TRY)
        dump2 = await page.evaluate(JS_DUMP)
        body = await page.locator('body').inner_text(timeout=5000)
        await page.screenshot(path=str(outdir / 'after.png'), full_page=True)

        data = {
            'dump_before': dump1,
            'try_result': tried,
            'dump_after': dump2,
            'body_prefix': body[:5000],
        }
        (outdir / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

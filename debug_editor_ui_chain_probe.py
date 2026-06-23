from __future__ import annotations
import asyncio, json, sys, time
from pathlib import Path
base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / 'src'))
from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / 'ck.txt'
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news'

JS = r'''() => {
  const out = {};
  const inst = window.UE_V2?.instants?.ueditorInstant0 || null;
  const UI = window['$' + 'EDITORUI_V2'] || null;
  out.hasInst = !!inst;
  out.hasUI = !!UI;
  out.instKeys = inst ? Object.keys(inst).slice(0,500) : [];
  out.uiKeys = UI ? Object.keys(UI).slice(0,500) : [];
  out.edui41 = (() => {
    const el = document.querySelector('#edui41, #edui41_state, .edui-for-bjhInsertionDrawer');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {tag:el.tagName,id:el.id||'',cls:String(el.className||''),text:(el.innerText||el.textContent||'').trim(),rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:el.outerHTML.slice(0,1000)};
  })();
  out.edui42 = (() => {
    const el = document.querySelector('#edui42');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {style: el.getAttribute('style'), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:el.outerHTML.slice(0,1500)};
  })();
  out.uiEdui41Type = UI?.edui41 ? typeof UI.edui41 : null;
  out.uiEdui42Type = UI?.edui42 ? typeof UI.edui42 : null;
  out.uiEdui41Keys = UI?.edui41 ? Object.keys(UI.edui41).slice(0,300) : [];
  out.uiEdui42Keys = UI?.edui42 ? Object.keys(UI.edui42).slice(0,300) : [];
  out.instCommandNames = inst?.commands ? Object.keys(inst.commands).slice(0,500) : [];
  out.importishCommands = out.instCommandNames.filter(k => /import|doc|word|insert|drawer|upload/i.test(k));
  out.instOptions = inst?.options ? Object.keys(inst.options).filter(k => /import|doc|word|insert|upload|drawer/i.test(k)).slice(0,200) : [];
  out.uiImportish = UI ? Object.keys(UI).filter(k => /import|doc|word|insert|upload|drawer|edui41|edui42/i.test(k)).slice(0,300) : [];
  out.uiEd41Importish = UI?.edui41 ? Object.keys(UI.edui41).filter(k => /show|popup|click|exec|items|menu|sub|drop|hover|insert|drawer|import|doc|word/i.test(k)).slice(0,300) : [];
  out.uiEd42Importish = UI?.edui42 ? Object.keys(UI.edui42).filter(k => /show|popup|click|exec|items|menu|sub|drop|hover|insert|drawer|import|doc|word/i.test(k)).slice(0,300) : [];
  out.importdocCmd = inst?.commands?.importdoc ? {
    keys: Object.keys(inst.commands.importdoc),
    exec: String(inst.commands.importdoc.execCommand || '').slice(0,2000),
    query: String(inst.commands.importdoc.queryCommandState || '').slice(0,1000),
  } : null;
  out.bjhInsertionDrawerCmd = inst?.commands?.bjhInsertionDrawer ? {
    keys: Object.keys(inst.commands.bjhInsertionDrawer),
    exec: String(inst.commands.bjhInsertionDrawer.execCommand || '').slice(0,2000),
  } : null;
  out.uiEd41Dump = UI?.edui41 ? JSON.stringify(Object.fromEntries(Object.keys(UI.edui41).filter(k => /show|popup|click|exec|items|menu|sub|drop|hover|insert|drawer|import|doc|word/i.test(k)).map(k => [k, typeof UI.edui41[k]]))).slice(0,4000) : null;
  return out;
}'''

async def main():
    outdir = base / 'debug' / 'editor_ui_chain_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_ui_chain_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1400, 'height': 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(10000)
        data = await page.evaluate(JS)
        (outdir / 'result.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

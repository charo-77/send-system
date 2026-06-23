from __future__ import annotations
import asyncio, json, sys, time
from pathlib import Path
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

JS=r'''
() => {
  const uiName = '$' + 'EDITORUI_V2';
  const UI = window[uiName];
  const safeKeys = obj => { try { return obj ? Object.keys(obj).slice(0,800) : null } catch(e) { return String(e) } };
  const out = {};
  out.globals = Object.keys(window).filter(k => /UE|EDITOR|edui|ueditor|import|doc|upload/i.test(k)).slice(0,800);
  out.UE_V2_type = typeof window.UE_V2;
  out.EDITORUI_type = typeof UI;
  out.UE_V2_keys = safeKeys(window.UE_V2);
  out.EDITORUI_keys = safeKeys(UI);
  out.instants_keys = safeKeys(window.UE_V2?.instants);
  const inst = window.UE_V2?.instants?.ueditorInstant0;
  out.inst_exists = !!inst;
  out.inst_keys = safeKeys(inst);
  out.inst_options_keys = safeKeys(inst?.options);
  out.inst_commands_keys = safeKeys(inst?.commands);
  out.inst_plugins_keys = safeKeys(inst?.plugins);
  out.inst_command_names_importish = out.inst_commands_keys ? out.inst_commands_keys.filter(k => /import|doc|word|upload|image|insert/i.test(k)) : null;
  out.inst_plugin_names_importish = out.inst_plugins_keys ? out.inst_plugins_keys.filter(k => /import|doc|word|upload|image|insert/i.test(k)) : null;
  out.ui_keys_importish = safeKeys(UI)?.filter(k => /edui|import|doc|word|upload|image|insert/i.test(k));
  out.ui_edui1_keys = safeKeys(UI?.edui1);
  out.ui_edui1_importish = safeKeys(UI?.edui1)?.filter(k => /import|doc|word|upload|dialog|button|toolbar|exec|command|image/i.test(k));
  out.command_importdoc_keys = inst?.commands?.importdoc ? Object.keys(inst.commands.importdoc) : null;
  out.command_importdoc_str = inst?.commands?.importdoc ? String(inst.commands.importdoc.execCommand || inst.commands.importdoc) .slice(0,1000) : null;
  out.hasExecCommand = typeof inst?.execCommand;
  out.hasFireEvent = typeof inst?.fireEvent;
  out.bodyText = inst?.body?.innerText?.slice(0,200) || null;
  out.bodyHTML = inst?.body?.innerHTML?.slice(0,500) || null;
  return out;
}
'''

async def main():
    outdir=base/'debug'/'editor_object_probe'; outdir.mkdir(parents=True,exist_ok=True)
    cookies=load_cookie_file(base/'ck.txt')
    async with async_playwright() as p:
        context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_editor_object_{int(time.time())}'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context,cookies)
        page=context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(10000)
        data=await page.evaluate(JS)
        (outdir/'result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(data,ensure_ascii=False,indent=2))
        await context.close()
if __name__=='__main__': asyncio.run(main())

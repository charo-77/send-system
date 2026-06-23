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

CK = base / 'ck.txt'
URL = 'https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1'

JS = r'''() => {
  const out = { steps: [] };
  const UI = window['$' + 'EDITORUI_V2'] || null;
  const inst = window.UE_V2?.instants?.ueditorInstant0 || null;
  const byId = id => document.getElementById(id);
  const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const rectOf = el => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};
  };
  const snap = label => {
    const ed41 = byId('edui41');
    const st41 = byId('edui41_state');
    const ed42 = byId('edui42');
    const c42 = byId('edui42_content');
    const fileInputs = Array.from(document.querySelectorAll('input[type=file]')).map((el, i) => ({
      i,
      accept: el.getAttribute('accept') || '',
      cls: String(el.className || ''),
      id: el.id || '',
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: rectOf(el),
      html: (el.outerHTML || '').slice(0, 220),
    }));
    const importNodes = Array.from(document.querySelectorAll('*')).map(el => ({
      tag: el.tagName,
      id: el.id || '',
      cls: String(el.className || ''),
      txt: textOf(el).slice(0, 120),
      rect: rectOf(el),
      html: (el.outerHTML || '').slice(0, 220),
    })).filter(x => x.rect && x.rect.w > 10 && x.rect.h > 10 && /导入文档|插入|Daoruwendang|importdoc|bjhInsertionDrawer|edui41|edui42/.test(x.txt + ' ' + x.id + ' ' + x.cls + ' ' + x.html)).slice(0, 80);
    out.steps.push({
      label,
      edui41: ed41 ? {text:textOf(ed41), rect:rectOf(ed41), cls:String(ed41.className||''), html:(ed41.outerHTML||'').slice(0,260)} : null,
      edui41_state: st41 ? {text:textOf(st41), rect:rectOf(st41), cls:String(st41.className||''), html:(st41.outerHTML||'').slice(0,260)} : null,
      edui42: ed42 ? {text:textOf(ed42), rect:rectOf(ed42), cls:String(ed42.className||''), style:ed42.getAttribute('style') || '', html:(ed42.outerHTML||'').slice(0,500)} : null,
      edui42_content: c42 ? {text:textOf(c42), rect:rectOf(c42), html:(c42.innerHTML||'').slice(0,800)} : null,
      fileInputs,
      importNodes,
      bodyHasImportDoc: (document.body.innerText || '').includes('导入文档'),
    });
  };

  snap('initial');

  try {
    const st = byId('edui41_state') || byId('edui41');
    if (st) {
      const r = st.getBoundingClientRect();
      const fire = type => st.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
      ['mouseover','mouseenter','mousemove','pointerover','pointerenter','pointermove'].forEach(fire);
      snap('after-hover-state');
      ['mousedown','mouseup','click'].forEach(fire);
      snap('after-click-state');
    }
  } catch (e) {
    out.steps.push({label:'error-state-events', error:String(e)});
  }

  try {
    const ed41ui = UI?.edui41 || null;
    if (ed41ui) {
      const proto = Object.getPrototypeOf(ed41ui);
      const methods = Array.from(new Set([
        ...Object.keys(ed41ui),
        ...(proto ? Object.getOwnPropertyNames(proto) : []),
      ])).filter(k => typeof ed41ui[k] === 'function' && /mouse|hover|show|popup|menu|stateful|click|over|down/i.test(k));
      out.ed41Methods = methods;
      for (const name of methods.slice(0, 50)) {
        try {
          ed41ui[name]({ type:'mouseover', button:0, target: byId('edui41_state') || byId('edui41') });
          snap('after-method-' + name);
          if ((document.body.innerText || '').includes('导入文档')) break;
          if (document.querySelector('#edui42_content')?.innerText?.includes('导入文档')) break;
        } catch (e) {
          out.steps.push({label:'method-error-' + name, error:String(e)});
        }
      }
    }
  } catch (e) {
    out.steps.push({label:'error-ed41-methods', error:String(e)});
  }

  try {
    if (inst?.commands) {
      for (const cmd of ['bjhInsertionDrawer', 'insertdoc', 'importdoc', 'openInsertionDrawer']) {
        if (inst.commands[cmd] && typeof inst.execCommand === 'function') {
          try {
            inst.execCommand(cmd);
            snap('after-exec-' + cmd);
          } catch (e) {
            out.steps.push({label:'exec-error-' + cmd, error:String(e)});
          }
        }
      }
    }
  } catch (e) {
    out.steps.push({label:'error-exec-commands', error:String(e)});
  }

  return out;
}'''


async def main():
    outdir = base / 'debug' / 'editor_insert_chain_closedloop'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_insert_closed_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_function("() => !!window['$' + 'EDITORUI_V2'] && !!window.UE_V2?.instants?.ueditorInstant0 && !!document.querySelector('#ueditor_0')", timeout=120000)
        await page.wait_for_timeout(8000)

        result = await page.evaluate(JS)
        await page.screenshot(path=str(outdir / 'after_probe.png'), full_page=True)
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'step_count': len(result.get('steps', [])),
            'last_step': result.get('steps', [])[-1] if result.get('steps') else None,
            'ed41Methods': result.get('ed41Methods', [])[:20],
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

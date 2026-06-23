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
URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1"

INIT_HOOK = r'''() => {
  if (window.__fileProbeInstalled) return true;
  window.__fileProbeInstalled = true;
  window.__fileProbeLog = [];
  const log = (type, data) => {
    try {
      window.__fileProbeLog.push({ t: Date.now(), type, data });
    } catch (_) {}
  };

  const describe = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
    return {
      tag: el.tagName || null,
      id: el.id || '',
      cls: String(el.className || ''),
      type: el.getAttribute ? (el.getAttribute('type') || '') : '',
      accept: el.getAttribute ? (el.getAttribute('accept') || '') : '',
      name: el.getAttribute ? (el.getAttribute('name') || '') : '',
      text: (el.innerText || el.textContent || '').slice(0, 120),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: (el.outerHTML || '').slice(0, 300),
      parentCls: String(el.parentElement?.className || ''),
    };
  };

  const origCreate = Document.prototype.createElement;
  Document.prototype.createElement = function(tagName, options) {
    const el = origCreate.call(this, tagName, options);
    try {
      if (String(tagName).toLowerCase() === 'input') {
        queueMicrotask(() => log('createElement:input', describe(el)));
        const origSetAttr = el.setAttribute?.bind(el);
        if (origSetAttr && !el.__probeWrappedSetAttr) {
          el.__probeWrappedSetAttr = true;
          el.setAttribute = function(name, value) {
            const res = origSetAttr(name, value);
            if (String(name).toLowerCase() === 'type' || String(name).toLowerCase() === 'accept') {
              log('input:setAttribute', { name, value, desc: describe(el) });
            }
            return res;
          };
        }
      }
    } catch (_) {}
    return el;
  };

  const origInputClick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function(...args) {
    try { log('input.click', describe(this)); } catch (_) {}
    return origInputClick.apply(this, args);
  };

  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes || []) {
        if (!(node instanceof Element)) continue;
        if (node.matches?.('input[type=file], input')) {
          log('dom:add', describe(node));
        }
        const inner = node.querySelectorAll?.('input[type=file], input') || [];
        inner.forEach(el => log('dom:add:desc', describe(el)));
      }
    }
  });
  mo.observe(document.documentElement || document.body, { childList: true, subtree: true });

  const origAttachShadow = Element.prototype.attachShadow;
  if (origAttachShadow && !Element.prototype.__probeShadowWrapped) {
    Element.prototype.__probeShadowWrapped = true;
    Element.prototype.attachShadow = function(init) {
      const shadow = origAttachShadow.call(this, init);
      try {
        log('attachShadow', { host: describe(this), mode: init?.mode || null });
        const smo = new MutationObserver((mutations) => {
          for (const m of mutations) {
            for (const node of m.addedNodes || []) {
              if (!(node instanceof Element)) continue;
              if (node.matches?.('input[type=file], input')) log('shadow:add', describe(node));
              const inner = node.querySelectorAll?.('input[type=file], input') || [];
              inner.forEach(el => log('shadow:add:desc', describe(el)));
            }
          }
        });
        smo.observe(shadow, { childList: true, subtree: true });
      } catch (_) {}
      return shadow;
    };
  }

  log('probe:installed', { url: location.href });
  return true;
}'''

SNAPSHOT_JS = r'''() => {
  const frames = Array.from(document.querySelectorAll('iframe')).map((el, i) => {
    const r = el.getBoundingClientRect();
    let sameOrigin = false;
    let inputs = [];
    try {
      sameOrigin = !!el.contentDocument;
      if (sameOrigin) {
        inputs = Array.from(el.contentDocument.querySelectorAll('input[type=file], input')).map(inp => ({
          tag: inp.tagName,
          type: inp.getAttribute('type') || '',
          accept: inp.getAttribute('accept') || '',
          cls: String(inp.className || ''),
          id: inp.id || '',
          text: (inp.innerText || inp.textContent || '').slice(0, 80),
          html: (inp.outerHTML || '').slice(0, 200),
        })).slice(0, 50);
      }
    } catch (_) {}
    return {
      i,
      src: el.getAttribute('src') || '',
      cls: String(el.className || ''),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      sameOrigin,
      inputs,
    };
  });

  const roots = [];
  const walk = (node) => {
    if (!(node instanceof Element)) return;
    if (node.shadowRoot) {
      const inputs = Array.from(node.shadowRoot.querySelectorAll('input[type=file], input')).map(inp => ({
        tag: inp.tagName,
        type: inp.getAttribute('type') || '',
        accept: inp.getAttribute('accept') || '',
        cls: String(inp.className || ''),
        id: inp.id || '',
        html: (inp.outerHTML || '').slice(0, 200),
      }));
      roots.push({ host: node.tagName, hostCls: String(node.className || ''), inputCount: inputs.length, inputs: inputs.slice(0, 20) });
      Array.from(node.shadowRoot.children).forEach(walk);
    }
    Array.from(node.children).forEach(walk);
  };
  walk(document.documentElement);

  return {
    url: location.href,
    bodyText: (document.body.innerText || '').slice(0, 5000),
    fileInputs: Array.from(document.querySelectorAll('input[type=file], input')).map((el, i) => {
      const r = el.getBoundingClientRect();
      return {
        i,
        tag: el.tagName,
        type: el.getAttribute('type') || '',
        accept: el.getAttribute('accept') || '',
        cls: String(el.className || ''),
        id: el.id || '',
        name: el.getAttribute('name') || '',
        rect: {x:r.x,y:r.y,w:r.width,h:r.height},
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
        html: (el.outerHTML || '').slice(0, 200),
      };
    }).slice(0, 200),
    frames,
    shadowRoots: roots,
    probeLogTail: (window.__fileProbeLog || []).slice(-200),
  };
}'''

TRIGGER_JS = r'''() => {
  const textOf = el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const keys = /插入|导入文档|文档|word|doc/i;
  const els = Array.from(document.querySelectorAll('button,div,span,a,[role=button]'))
    .filter(el => visible(el) && keys.test(textOf(el) + ' ' + String(el.className || '') + ' ' + (el.outerHTML || '').slice(0, 200)))
    .map(el => {
      const r = el.getBoundingClientRect();
      return { el, txt: textOf(el), cls: String(el.className || ''), rect: {x:r.x,y:r.y,w:r.width,h:r.height} };
    })
    .filter(x => x.rect.w > 20 && x.rect.h > 20)
    .slice(0, 40);

  const clicked = [];
  for (const x of els) {
    try {
      if (typeof x.el.click === 'function') x.el.click();
      x.el.dispatchEvent(new MouseEvent('click', { bubbles:true, cancelable:true, view:window }));
      clicked.push({ txt: x.txt, cls: x.cls, rect: x.rect });
    } catch (_) {}
  }
  return { candidates: els.map(x => ({txt:x.txt, cls:x.cls, rect:x.rect})), clicked };
}'''


async def main():
    outdir = base / 'debug' / 'dynamic_fileinput_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_dynprobe_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await context.add_init_script(INIT_HOOK)
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(10000)
        await page.evaluate(INIT_HOOK)

        snapshots = []
        snapshots.append({'stage': 'initial', 'data': await page.evaluate(SNAPSHOT_JS)})
        await page.screenshot(path=str(outdir / '01_initial.png'), full_page=True)

        trigger = await page.evaluate(TRIGGER_JS)
        await page.wait_for_timeout(5000)
        snapshots.append({'stage': 'after_trigger', 'trigger': trigger, 'data': await page.evaluate(SNAPSHOT_JS)})
        await page.screenshot(path=str(outdir / '02_after_trigger.png'), full_page=True)

        for i in range(6):
            await page.wait_for_timeout(3000)
            snapshots.append({'stage': f'poll_{i}', 'data': await page.evaluate(SNAPSHOT_JS)})

        result = {'snapshots': snapshots}
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'stages': [x['stage'] for x in snapshots],
            'initial_inputs': len(snapshots[0]['data'].get('fileInputs', [])),
            'after_trigger_inputs': len(snapshots[1]['data'].get('fileInputs', [])),
            'probe_events': len(snapshots[-1]['data'].get('probeLogTail', [])),
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

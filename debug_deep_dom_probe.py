from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
base = Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright

JS = r"""
() => {
  const rows = [];
  const seen = new Set();
  function walk(root, prefix='') {
    const all = root.querySelectorAll ? Array.from(root.querySelectorAll('*')) : [];
    for (const el of all) {
      if (seen.has(el)) continue;
      seen.add(el);
      const r = el.getBoundingClientRect();
      const txt = (el.innerText || el.value || el.textContent || '').trim().replace(/\s+/g, ' ');
      const cls = String(el.className || '');
      const interesting =
        el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable ||
        el.getAttribute('contenteditable') != null || el.getAttribute('role') === 'textbox' ||
        el.tagName === 'IFRAME' || /editor|title|input|textarea|ueditor|article|content|publish|正文|标题/i.test(cls + ' ' + el.id + ' ' + txt + ' ' + (el.getAttribute('placeholder')||''));
      if (interesting) {
        const s = getComputedStyle(el);
        rows.push({
          tag: el.tagName, cls, id: el.id || '', name: el.getAttribute('name'), type: el.getAttribute('type'),
          role: el.getAttribute('role'), ceAttr: el.getAttribute('contenteditable'), isCE: el.isContentEditable,
          placeholder: el.getAttribute('placeholder'), aria: el.getAttribute('aria-label'),
          txt: txt.slice(0,180), value: (el.value || '').slice(0,180),
          rect: {x:r.x,y:r.y,w:r.width,h:r.height}, visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
          font: s.fontSize, weight: s.fontWeight, display: s.display, visibility: s.visibility,
          path: prefix
        });
      }
      if (el.shadowRoot) walk(el.shadowRoot, prefix + ' shadow<' + el.tagName + '>');
    }
  }
  walk(document);
  return {url: location.href, ready: document.readyState, body: (document.body?.innerText || '').slice(0,1000), rows: rows.slice(0,1000)};
}
"""

async def main():
    outdir = base / 'debug' / 'deep_dom_probe'; outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(base / 'ck.txt')
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(base / 'edge_profile_deep_dom'), channel='msedge', headless=False, viewport={'width':1400,'height':900}, args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0], wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(12000)
        data = await page.evaluate(JS)
        # also inspect frames if accessible
        frame_rows = []
        for fr in page.frames:
            try:
                frame_rows.append({'url': fr.url, 'data': await fr.evaluate(JS)})
            except Exception as e:
                frame_rows.append({'url': fr.url, 'error': str(e)[:300]})
        data['frames'] = frame_rows
        (outdir/'deep_dom.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.screenshot(path=str(outdir/'deep_dom.png'), full_page=True)
        print(json.dumps({'body': data['body'], 'rows': data['rows'][:80], 'frames': [{'url': x.get('url'), 'err': x.get('error'), 'rowCount': len(x.get('data',{}).get('rows',[])) if x.get('data') else None} for x in frame_rows]}, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__': asyncio.run(main())

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

FIND_AND_CLICK_INSERT = r'''() => {
  const textOf = el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 10 && r.height > 10 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const scoreOf = el => {
    const txt = textOf(el);
    const cls = String(el.className || '');
    const html = (el.outerHTML || '').slice(0, 500);
    const r = el.getBoundingClientRect();
    let score = 0;
    if (txt === '插入') score += 300;
    else if (txt.includes('插入')) score += 180;
    if (/entry|insert|toolbar|editor|FeEditorApp/i.test(cls + ' ' + html)) score += 120;
    if (r.y > 80 && r.y < 400) score += 60;
    if (r.x > 150 && r.x < 900) score += 40;
    return score;
  };

  const candidates = Array.from(document.querySelectorAll('button,div,span,a,[role=button]'))
    .filter(visible)
    .map(el => {
      const r = el.getBoundingClientRect();
      return { el, txt: textOf(el), cls: String(el.className || ''), rect: {x:r.x,y:r.y,w:r.width,h:r.height}, score: scoreOf(el) };
    })
    .filter(x => x.score >= 250)
    .sort((a, b) => b.score - a.score || a.rect.y - b.rect.y || a.rect.x - b.rect.x);

  const picked = candidates[0];
  if (!picked) return { found: false, candidates: candidates.slice(0, 20) };
  try {
    if (typeof picked.el.click === 'function') picked.el.click();
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      picked.el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window }));
    }
  } catch (_) {}
  return {
    found: true,
    picked: { txt: picked.txt, cls: picked.cls, rect: picked.rect, score: picked.score },
    candidates: candidates.slice(0, 10).map(x => ({ txt:x.txt, cls:x.cls, rect:x.rect, score:x.score })),
  };
}'''

SNAP = r'''() => ({
  bodyText: (document.body.innerText || '').slice(0, 5000),
  menuCandidates: Array.from(document.querySelectorAll('div,button,span,a')).map(el => {
    const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    const cls = String(el.className || '');
    const r = el.getBoundingClientRect();
    return { txt, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, html:(el.outerHTML||'').slice(0, 220) };
  }).filter(x => x.rect.w > 20 && x.rect.h > 20 && /导入文档|插入|Daoruwendang|9d63bce81e3a0b19-item|items|popover|dropdown|drawer/i.test(x.txt + ' ' + x.cls + ' ' + x.html)).slice(0, 80),
  fileInputs: Array.from(document.querySelectorAll('input[type=file]')).map(el => ({
    accept: el.getAttribute('accept') || '',
    cls: String(el.className || ''),
    html: (el.outerHTML || '').slice(0, 200)
  })),
  dialogs: Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="drawer"], [class*="modal"], [class*="popup"], [class*="popover"]')).map(el => {
    const r = el.getBoundingClientRect();
    return { cls: String(el.className || '').slice(0,120), txt: (el.innerText || '').slice(0,150), rect:{x:r.x,y:r.y,w:r.width,h:r.height} };
  }).filter(x => x.rect.w > 40 && x.rect.h > 20).slice(0, 30)
})'''


async def main():
    outdir = base / 'debug' / 'precise_insert_probe'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_precise_insert_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(10000)

        before = await page.evaluate(SNAP)
        click = await page.evaluate(FIND_AND_CLICK_INSERT)
        await page.wait_for_timeout(3000)
        after = await page.evaluate(SNAP)
        await page.screenshot(path=str(outdir / 'after_click_insert.png'), full_page=True)

        result = { 'before': before, 'click': click, 'after': after }
        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'clicked': click.get('found'),
            'picked': click.get('picked'),
            'after_menu_candidates': len(after.get('menuCandidates', [])),
            'after_file_inputs': after.get('fileInputs', []),
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

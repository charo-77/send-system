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
URL = "https://baijiahao.baidu.com/"

JS_FIND = r'''() => {
  return Array.from(document.querySelectorAll('*')).map((el, i) => {
    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {
      i, tag: el.tagName, id: el.id || '', cls: String(el.className || ''), txt: txt.slice(0, 120),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      cursor: cs.cursor,
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: el.outerHTML.slice(0, 350),
    };
  }).filter(x => x.visible && /发布作品|发布|图文|文章|视频|动态|直播|合集|图集/i.test([x.id,x.cls,x.txt,x.html].join(' '))).slice(0, 300)
}'''

async def click_text(page, text: str):
    loc = page.get_by_text(text, exact=True)
    cnt = await loc.count()
    for i in range(min(cnt, 5)):
        try:
            el = loc.nth(i)
            if await el.is_visible(timeout=1000):
                await el.click(timeout=3000)
                return True
        except Exception:
            pass
    return False

async def dump(page, outdir: Path, name: str):
    body = await page.locator('body').inner_text(timeout=5000)
    items = await page.evaluate(JS_FIND)
    await page.screenshot(path=str(outdir / f'{name}.png'), full_page=True)
    data = {'url': page.url, 'title': await page.title(), 'body_prefix': body[:5000], 'items': items}
    (outdir / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data

async def main():
    outdir = base / 'debug' / 'publish_entry_flow'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_publish_entry_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(8000)

        result = {'steps': []}
        result['steps'].append({'stage': 'home', **(await dump(page, outdir, '01_home'))})

        for text in ['发布作品', '图文', '文章']:
            ok = await click_text(page, text)
            result['steps'].append({'action': f'click:{text}', 'ok': ok, 'url_after': page.url})
            await page.wait_for_timeout(5000)
            result['steps'].append({'stage': f'after_{text}', **(await dump(page, outdir, f'after_{text}'))})
            if 'edit' in page.url or 'builder' in page.url and text != '发布作品':
                break

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

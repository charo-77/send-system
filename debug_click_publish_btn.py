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

JS_SCAN = r'''() => {
  return Array.from(document.querySelectorAll('*')).map((el, i) => {
    const txt = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {
      i,
      tag: el.tagName,
      id: el.id || '',
      cls: String(el.className || ''),
      txt: txt.slice(0, 160),
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      cursor: cs.cursor,
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      html: el.outerHTML.slice(0, 400),
    };
  }).filter(x => x.visible && /发布作品|图文|文章|视频|动态|直播|合集|短内容|图集/i.test([x.id,x.cls,x.txt,x.html].join(' '))).slice(0, 400)
}'''

async def dump(page, outdir: Path, name: str):
    body = await page.locator('body').inner_text(timeout=5000)
    items = await page.evaluate(JS_SCAN)
    await page.screenshot(path=str(outdir / f'{name}.png'), full_page=True)
    data = {'url': page.url, 'title': await page.title(), 'body_prefix': body[:5000], 'items': items}
    (outdir / f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data

async def safe_click(locator):
    try:
        await locator.click(timeout=3000)
        return 'click'
    except Exception:
        pass
    try:
        await locator.click(timeout=3000, force=True)
        return 'force_click'
    except Exception:
        pass
    return None

async def main():
    outdir = base / 'debug' / 'click_publish_btn'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_click_publish_{int(time.time())}'),
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

        btn = page.locator('#home-publish-btn')
        expand = page.locator('#home-publish-btn .FeReactApp-_4f4cb3a3b81b55a5-expandContent')
        how = None

        if await btn.count():
            how = await safe_click(btn)
        if not how and await expand.count():
            how = await safe_click(expand)
        if not how:
            box = await btn.bounding_box()
            if box:
                await page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                how = 'mouse_center'
        if not how:
            ok = await page.evaluate("""() => {
              const el = document.querySelector('#home-publish-btn');
              if (!el) return false;
              el.click();
              return true;
            }""")
            if ok:
                how = 'dom_click'

        result['steps'].append({'action': 'click_publish_btn', 'how': how, 'url_after': page.url})
        await page.wait_for_timeout(4000)
        result['steps'].append({'stage': 'after_publish_click', **(await dump(page, outdir, '02_after_publish_click'))})

        for text in ['图文', '文章', '发布文章']:
            try:
                loc = page.get_by_text(text, exact=True)
                cnt = await loc.count()
                clicked = False
                for i in range(min(cnt, 5)):
                    el = loc.nth(i)
                    if await el.is_visible(timeout=1000):
                        try:
                            await el.click(timeout=3000)
                            clicked = True
                            break
                        except Exception:
                            try:
                                await el.click(timeout=3000, force=True)
                                clicked = True
                                break
                            except Exception:
                                pass
                result['steps'].append({'action': f'click_option:{text}', 'clicked': clicked, 'url_after': page.url})
                await page.wait_for_timeout(5000)
                result['steps'].append({'stage': f'after_option_{text}', **(await dump(page, outdir, f'03_after_option_{text}'))})
                if clicked and page.url != URL:
                    break
            except Exception as e:
                result['steps'].append({'action': f'click_option:{text}', 'error': str(e)})

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

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

FINDERS = [
    "text=发布文章",
    "text=发布图文",
    "text=图文",
    "text=写文章",
    "text=发布内容",
]

async def dump_page(page, outdir: Path, tag: str):
    body = await page.locator('body').inner_text(timeout=5000)
    data = await page.evaluate(
        """() => Array.from(document.querySelectorAll('*')).map((el, i) => {
          const txt = (el.innerText || el.textContent || '').trim();
          const r = el.getBoundingClientRect();
          return {
            i,
            tag: el.tagName,
            id: el.id || '',
            cls: String(el.className || ''),
            txt: txt.slice(0, 120),
            visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
            rect: {x:r.x, y:r.y, w:r.width, h:r.height},
            html: el.outerHTML.slice(0, 300),
          };
        }).filter(x => /发布文章|发布图文|写文章|图文|文章|发布内容/i.test([x.id, x.cls, x.txt, x.html].join(' '))).slice(0, 200)"""
    )
    payload = {
        'url': page.url,
        'title': await page.title(),
        'body_prefix': body[:5000],
        'matches': data,
    }
    (outdir / f'{tag}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(outdir / f'{tag}.png'), full_page=True)
    return payload

async def try_click(page, text_selector: str):
    loc = page.locator(text_selector)
    n = await loc.count()
    if n == 0:
        return False
    for i in range(min(n, 5)):
        el = loc.nth(i)
        try:
            if await el.is_visible(timeout=1000):
                await el.click(timeout=3000)
                return True
        except Exception:
            pass
    return False

async def main():
    outdir = base / 'debug' / 'start_article_flow'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_start_article_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(5000)

        result = {'steps': []}
        result['steps'].append({'stage': 'home', **(await dump_page(page, outdir, '01_home'))})

        clicked = False
        clicked_selector = None
        for sel in FINDERS:
            ok = await try_click(page, sel)
            result['steps'].append({'try_selector': sel, 'clicked': ok, 'url_after': page.url})
            if ok:
                clicked = True
                clicked_selector = sel
                break

        if clicked:
            await page.wait_for_timeout(6000)
            result['steps'].append({'stage': 'after_click', 'clicked_selector': clicked_selector, **(await dump_page(page, outdir, '02_after_click'))})

            # if still on homepage, also try direct article editor link by visible 图文 tile
            if 'builder/rc/edit' not in page.url and 'edit' not in page.url:
                # click candidate element by text 图文 if still available
                await try_click(page, 'text=图文')
                await page.wait_for_timeout(6000)
                result['steps'].append({'stage': 'after_fallback_tuwen', **(await dump_page(page, outdir, '03_after_fallback_tuwen'))})
        else:
            result['steps'].append({'stage': 'no_click_target_found'})

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()

if __name__ == '__main__':
    asyncio.run(main())

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright
from cookies import load_cookie_file
from browser_publish import inject_cookies


INPUT_SEL = (
    'input[type="file"][name="file"][accept*=".docx" i], '
    'input[type="file"][accept*=".docx" i], '
    'input[type="file"][accept*="doc" i], '
    'input[type="file"][accept*="word" i], '
    'input[type="file"][accept*="application" i], '
    'input[type="file"]:not([accept*="video" i]):not([accept*="image" i])'
)


async def safe_title(page):
    try:
        return await page.title()
    except Exception as e:
        return f'<title_error:{e}>'


async def snap(page, name: str, out_dir: Path):
    payload = {"name": name}
    try:
        payload["url"] = page.url
    except Exception as e:
        payload["url_error"] = str(e)
    payload["title"] = await safe_title(page)
    try:
        payload["body"] = (await page.locator("body").inner_text(timeout=3000))[:3000]
    except Exception as e:
        payload["body_error"] = str(e)
    try:
        payload["file_input_count"] = await page.locator(INPUT_SEL).count()
    except Exception as e:
        payload["file_input_error"] = str(e)
    (out_dir / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def wait_editorish(page, out_dir: Path):
    for i, ms in enumerate([3000, 5000, 8000, 12000, 15000], start=1):
        await page.wait_for_timeout(ms)
        await snap(page, f'wait_{i}_{ms}ms', out_dir)
        try:
            ok = await page.evaluate(r'''() => {
                return !!document.querySelector('iframe#ueditor_0')
                    || !!document.querySelector('[data-testid="news-title-input"] [contenteditable="true"][data-lexical-editor="true"]')
                    || !!Array.from(document.querySelectorAll('button,[role="button"],div,span,a')).find(el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim()).includes('导入文档'));
            }''')
        except Exception as e:
            (out_dir / f'wait_{i}_{ms}ms_probe_error.txt').write_text(str(e), encoding='utf-8')
            return False
        if ok:
            (out_dir / 'editorish_ready.txt').write_text(f'ready_after={ms}', encoding='utf-8')
            return True
    return False


async def click_import(page):
    return await page.evaluate(r'''() => {
        const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
        const visible = el => {
            const r = el.getBoundingClientRect();
            return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0;
        };

        const direct = Array.from(document.querySelectorAll('button,[role="button"],div,span,a,li,[role="menuitem"]'))
            .find(el => visible(el) && textOf(el).includes('导入文档'));
        if (direct) {
            const r = direct.getBoundingClientRect();
            try { if (typeof direct.click === 'function') direct.click(); } catch (_) {}
            for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                direct.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
            }
            return { strategy: 'direct', text: textOf(direct), cls: String(direct.className || '') };
        }

        const insert = document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry') || document.querySelector('#edui41_state') || document.querySelector('#edui41');
        if (!insert) return { strategy: 'none' };
        const r1 = insert.getBoundingClientRect();
        try { if (typeof insert.click === 'function') insert.click(); } catch (_) {}
        for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
            insert.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r1.x+r1.width/2, clientY:r1.y+r1.height/2, button:0 }));
        }

        const items = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-item, [role="menuitem"], li, div'));
        const picked = items.find(el => visible(el) && !!el.querySelector('.l-icon-BjhBasicDaoruwendang'))
            || items.find(el => visible(el) && textOf(el).includes('导入文档'))
            || null;
        if (!picked) {
            return { strategy: 'insert-only', itemCount: items.length, sampleTexts: items.map(textOf).filter(Boolean).slice(0, 20) };
        }
        const r2 = picked.getBoundingClientRect();
        try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
        for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
            picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r2.x+r2.width/2, clientY:r2.y+r2.height/2, button:0 }));
        }
        return { strategy: 'insert-menu', text: textOf(picked), cls: String(picked.className || '') };
    }''')


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile-dir', required=True)
    ap.add_argument('--cookie-file', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(Path(args.cookie_file))

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(Path(args.profile_dir)),
            executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        if cookies:
            await inject_cookies(context, cookies)
        await page.goto('https://baijiahao.baidu.com/builder/rc/edit?type=news', wait_until='domcontentloaded', timeout=60000)
        await snap(page, '01_after_goto', out_dir)
        ready = await wait_editorish(page, out_dir)
        (out_dir / 'editorish_ready.json').write_text(json.dumps({"ready": ready}, ensure_ascii=False, indent=2), encoding='utf-8')
        click_result = await click_import(page)
        (out_dir / '04_click_import.json').write_text(json.dumps(click_result, ensure_ascii=False, indent=2), encoding='utf-8')
        await page.wait_for_timeout(2500)
        await snap(page, '05_after_click_import', out_dir)
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

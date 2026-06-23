"""
debug_insert_v12.py
关键洞察：edui42_content display:block but rect={0,0,0,0} → CSS 布局未完成
分阶段检查 hover 后 0.5s, 1s, 2s, 3s 的状态变化
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))
from cookies import load_cookie_file as load_cookies
from browser_publish import inject_cookies as inject_cookies_func

PUBLISH_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"
PROJECT_DIR = Path(__file__).parent
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v12"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def js_filter_visible(items):
    """Python-side filter for JS results that include 'visible' key."""
    return [x for x in items if x.get('visible')]


async def main():
    cookie_path = PROJECT_DIR / "ck.txt"
    cookies = load_cookies(cookie_path)
    print(f"[COOKIES] loaded {len(cookies)} items")

    result = {"url": PUBLISH_URL, "steps": []}

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROJECT_DIR / "bjh_browser_data"),
            channel="msedge",
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await inject_cookies_func(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        for text in ["我知道了", "下一步", "取消"]:
            try:
                btn = page.get_by_text(text, exact=False).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        await page.wait_for_selector("#ueditor", timeout=30000)
        await page.wait_for_selector("iframe#ueditor_0", timeout=30000)
        await page.wait_for_timeout(2000)
        print("[PAGE] editor ready")

        eval_result = await page.evaluate("""() => {
            try {
                var el = document.getElementById('edui41_state');
                if (!el) return {error: 'no edui41_state'};
                var r = el.getBoundingClientRect();
                return {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: el.innerText ? el.innerText.trim() : ''};
            } catch(e) {
                return {error: e.message};
            }
        }""")
        state_rect = eval_result if isinstance(eval_result, dict) and 'error' not in eval_result else None
        print(f"[STATE] rect={state_rect}, eval_result={eval_result}")

        # hover
        await page.mouse.move(state_rect['cx'], state_rect['cy'])
        result["steps"].append({"step": "hover", "x": state_rect['cx'], "y": state_rect['cy']})
        print("[HOVER] mouse moved")

        # 分阶段检查：hover 后 0.5s, 1s, 2s, 3s
        checkpoints = [500, 1000, 2000, 3000]
        total_waited = 0

        for wait_t in checkpoints:
            additional_wait = wait_t - total_waited
            if additional_wait > 0:
                await page.wait_for_timeout(additional_wait)
                total_waited = wait_t

            snap = await page.evaluate("""() => {
                var content = document.getElementById('edui42_content');
                var e42 = document.getElementById('edui42');
                var e43 = document.getElementById('edui43');
                return {
                    content_display: content ? getComputedStyle(content).display : null,
                    content_rect: content ? (function() { var r=content.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })() : null,
                    content_text: content ? (content.innerText||'').trim().slice(0,300) : null,
                    content_innerHTML: content ? content.innerHTML.slice(0, 800) : null,
                    content_childCount: content ? content.children.length : null,
                    e42_display: e42 ? getComputedStyle(e42).display : null,
                    e43_visible: e43 ? (function() { var r=e43.getBoundingClientRect(); return r.width>0&&r.height>0; })() : null,
                    e43_text: e43 ? (e43.innerText||'').trim().slice(0,200) : null,
                    file_inputs: Array.from(document.querySelectorAll('#edui42_content input[type=file]')).map(function(el) {
                        return {accept: el.accept, visible: el.offsetWidth>0&&el.offsetHeight>0, rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })()};
                    }),
                    import_els: Array.from(document.querySelectorAll('*')).filter(function(el) { return (el.innerText||'').trim().includes('导入文档') || (el.innerText||'').trim().includes('导入'); }).map(function(el) { var r=el.getBoundingClientRect(); return {id:el.id,text:(el.innerText||'').trim().slice(0,100),visible:r.width>0&&r.height>0}; }),
                };
            }""")
            print(f"\n[T={wait_t}ms] content_display={snap.get('content_display')} content_childCount={snap.get('content_childCount')} rect={snap.get('content_rect')}")
            print(f"[T={wait_t}ms] content_text={repr(snap.get('content_text','')[:150])}")
            print(f"[T={wait_t}ms] e42_display={snap.get('e42_display')} e43_visible={(snap.get('e43_visible') or False)} e43_text={repr((snap.get('e43_text') or '')[:80])}")

            visible_fi = [fi for fi in snap.get('file_inputs', []) if fi.get('visible')]
            visible_ie = [ie for ie in snap.get('import_els', []) if ie.get('visible')]
            print(f"[T={wait_t}ms] file_inputs(visible)={len(visible_fi)} import_els(visible)={len(visible_ie)}")
            for fi in visible_fi:
                print(f"  ** FILE INPUT: accept={fi['accept']!r} rect={fi['rect']}")
            for ie in visible_ie:
                print(f"  ** IMPORT EL: [{ie['id']}] rect={ie['rect']} text={repr(ie['text'])}")

            result[f"t_{wait_t}ms"] = snap

            if snap.get('content_childCount', 0) > 0:
                await page.screenshot(path=str(DEBUG_DIR / f"t_{wait_t}ms.png"), full_page=True)

        # click if no results
        has_file = any(result.get(f't_{t}ms', {}).get('file_inputs', []) for t in checkpoints)
        has_import = any([ie for ie in result.get(f't_{t}ms', {}).get('import_els', []) if ie.get('visible')] for t in checkpoints)

        if not has_file and not has_import:
            print("\n[TRYING] click on edui41_state")
            await page.mouse.click(state_rect['cx'], state_rect['cy'])
            await page.wait_for_timeout(2000)

            after_click = await page.evaluate("""() => {
                var content = document.getElementById('edui42_content');
                return {
                    content_display: content ? getComputedStyle(content).display : null,
                    content_text: content ? (content.innerText||'').trim().slice(0,300) : null,
                    content_innerHTML: content ? content.innerHTML.slice(0, 800) : null,
                    content_childCount: content ? content.children.length : null,
                    file_inputs: Array.from(document.querySelectorAll('#edui42_content input[type=file]')).map(function(el) {
                        return {accept: el.accept, visible: el.offsetWidth>0&&el.offsetHeight>0, rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })()};
                    }),
                    import_els: Array.from(document.querySelectorAll('*')).filter(function(el) { return (el.innerText||'').trim().includes('导入文档') || (el.innerText||'').trim().includes('导入'); }).map(function(el) { var r=el.getBoundingClientRect(); return {id:el.id,text:(el.innerText||'').trim().slice(0,100),visible:r.width>0&&r.height>0}; }),
                };
            }""")
            result["after_click"] = after_click
            print(f"[AFTER CLICK] content_childCount={after_click.get('content_childCount')} content_text={repr(after_click.get('content_text','')[:150])}")
            for fi in [f for f in after_click.get('file_inputs', []) if f.get('visible')]:
                print(f"  ** FILE INPUT: accept={fi['accept']!r} rect={fi['rect']}")
            await page.screenshot(path=str(DEBUG_DIR / "after_click.png"), full_page=True)

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
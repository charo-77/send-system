"""
debug_insert_v10.py
关键发现：Playwright locator.hover/click 被透明遮罩层拦截
<rect y="0" x="258.5" ... pointer-events="auto"></rect> from <div> subtree intercepts pointer events

透明遮罩是百家号编辑器的 article editor overlay (id=edui3_article)

解决方案：
1. page.mouse.click(x, y) - 直接用绝对坐标，绕过 Playwright action 系统
2. locator.hover/click(force=True) - 强制点击，忽略拦截检查
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v10"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


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
        await page.wait_for_timeout(3000)
        print("[PAGE] editor ready")

        # 探查遮罩层
        overlay_info = await page.evaluate("""() => {
            // 找所有拦截指针的元素
            var candidates = Array.from(document.querySelectorAll('div, span, section'))
                .filter(function(el) {
                    var r = el.getBoundingClientRect();
                    return r.width > 500 && r.height > 500 && r.x >= 200;
                })
                .map(function(el) {
                    var style = getComputedStyle(el);
                    return {
                        id: el.id, cls: el.className.toString().slice(0, 60),
                        rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                        pointerEvents: style.pointerEvents,
                        display: style.display,
                        opacity: style.opacity,
                        zIndex: style.zIndex,
                        text: (el.innerText||'').trim().slice(0, 50)
                    };
                });
            return {
                candidates: candidates,
                body_rect: (function() { var r=document.body.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })()
            };
        }""")
        result["overlay_info"] = overlay_info
        print(f"[OVERLAY] candidates={len(overlay_info.get('candidates', []))}")
        for c in overlay_info.get('candidates', [])[:5]:
            print(f"  [{c['id']}] cls={c['cls']} pointerEvents={c['pointerEvents']} rect={c['rect']} text={c['text']}")

        # 获取 edui41_state 位置
        state_rect = await page.evaluate("""() => {
            var el = document.getElementById('edui41_state');
            if (!el) return null;
            var r = el.getBoundingClientRect();
            return {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: el.innerText.trim()};
        }""")
        print(f"[STATE] rect={state_rect}")
        result["state_rect"] = state_rect

        cx, cy = state_rect['cx'], state_rect['cy']

        # ── 方法1：page.mouse.move/click (绕过 action 系统) ────
        print(f"\n[METHOD1] page.mouse.move({cx}, {cy})")
        await page.mouse.move(cx, cy)
        print("[METHOD1] moved")
        await page.wait_for_timeout(1500)

        # 检查 hover 后状态
        check1 = await page.evaluate("""() => {
            var e42 = document.getElementById('edui42');
            var e43 = document.getElementById('edui43');
            var getInfo = function(id) {
                var el = document.getElementById(id);
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
            };
            return {edui42: getInfo('edui42'), edui43: getInfo('edui43')};
        }""")
        result["check1"] = check1
        print(f"[CHECK1] edui42 display={check1.get('edui42',{}).get('display')} visible={check1.get('edui42',{}).get('visible')} rect={check1.get('edui42',{}).get('rect')}")
        print(f"[CHECK1] edui43 display={(check1.get('edui43') or {}).get('display')} visible={(check1.get('edui43') or {}).get('visible')} text={repr((check1.get('edui43') or {}).get('text','')[:100])}")

        # ── 方法2：click 然后等菜单出现 ─────────────────────
        if not check1.get('edui42', {}).get('visible'):
            print(f"\n[METHOD2] page.mouse.click({cx}, {cy})")
            await page.mouse.click(cx, cy)
            await page.wait_for_timeout(2000)

            check2 = await page.evaluate("""() => {
                var e42 = document.getElementById('edui42');
                if (!e42) return null;
                var r = e42.getBoundingClientRect();
                return {display: getComputedStyle(e42).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (e42.innerText||'').trim().slice(0,300), html: e42.innerHTML.slice(0,800)};
            }""")
            result["check2"] = check2
            print(f"[CHECK2] edui42 display={check2.get('display')} visible={check2.get('visible')} rect={check2.get('rect')}")
            print(f"[CHECK2] text={repr(check2.get('text','')[:200])}")
            if check2.get('html'):
                print(f"[CHECK2] html={check2['html'][:400]}")

        # ── 方法3：locator.hover(force=True) ─────────────────
        if not check1.get('edui42', {}).get('visible') and not (check2 and check2.get('visible')):
            print(f"\n[METHOD3] locator.hover(force=True)")
            try:
                await page.locator("#edui41_state").hover(force=True, timeout=5000)
                print("[METHOD3] hovered with force=True")
            except Exception as e:
                print(f"[METHOD3 error] {e}")
            await page.wait_for_timeout(1500)

            check3 = await page.evaluate("""() => {
                var e42 = document.getElementById('edui42');
                if (!e42) return null;
                var r = e42.getBoundingClientRect();
                return {display: getComputedStyle(e42).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (e42.innerText||'').trim().slice(0,300), html: e42.innerHTML.slice(0,500)};
            }""")
            result["check3"] = check3
            print(f"[CHECK3] edui42 display={check3.get('display')} visible={check3.get('visible')} rect={check3.get('rect')}")

        # ── 最终：找 file input ──────────────────────────
        final = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type=file]')).map(function(el) {
                return {
                    accept: el.accept,
                    hidden: el.hidden || el.style.display === 'none',
                    visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                    rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                    parent: el.parentElement ? el.parentElement.className.toString().slice(0, 60) : ''
                };
            });
        }""")
        result["final"] = final
        print(f"\n[FINAL] file_inputs={len(final)}")
        for fi in final:
            print(f"  accept={fi['accept']!r} visible={fi['visible']} rect={fi['rect']} parent={fi['parent']}")

        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_v10.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
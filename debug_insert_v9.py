"""
debug_insert_v9.py
probe2 发现：hover edui41_state → edui42 display:block
当前 v8 测试：hover 后 edui42 还是 display:none

差异原因：probe2 的 hover 是在真实浏览器页面操作，而 v8 的 page.mouse.move 可能有差异
或页面状态不同（probe2 在之前的测试中页面已经处于 hover 状态）

新方案：
1. 直接在页面上执行 mouseover + mousemove + mousedown + mouseup 的完整 JS 事件序列
   触发 edui41_state 上的 React synthetic event
2. 或者直接用 Playwright locator hover 然后等待 CSS transition

核心：百家号的工具栏是 React 组件，用的是 React 的合成事件系统 (onMouseDown/Over/Out)
不是原生 addEventListener。需要用 Playwright 的 .hover() 才能触发。
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v9"
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

        # ── 方法1：Playwright locator.hover() + waitForTimeout ─
        print("\n[METHOD1] locator.hover() + CSS transition")
        try:
            locator = page.locator("#edui41_state")
            await locator.hover(timeout=5000)
            print("[METHOD1] hovered via locator.hover()")
        except Exception as e:
            print(f"[METHOD1 error] {e}")
        await page.wait_for_timeout(1500)

        check1 = await page.evaluate("""() => {
            var e41 = document.getElementById('edui41');
            var e42 = document.getElementById('edui42');
            var e43 = document.getElementById('edui43');
            var getInfo = function(id) {
                var el = document.getElementById(id);
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {
                    display: getComputedStyle(el).display,
                    visible: r.width>0&&r.height>0,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0,200),
                    html: el.innerHTML.slice(0,300),
                };
            };
            return {edui41: getInfo('edui41'), edui42: getInfo('edui42'), edui43: getInfo('edui43')};
        }""")
        result["check1"] = check1
        print(f"[CHECK1] edui41 text={check1.get('edui41',{}).get('text')} rect={check1.get('edui41',{}).get('rect')}")
        print(f"[CHECK1] edui42 display={check1.get('edui42',{}).get('display')} visible={check1.get('edui42',{}).get('visible')} text={repr(check1.get('edui42',{}).get('text','')[:100])}")

        # ── 方法2：mousedown + mouseup + click ─────────────
        if not check1.get('edui42', {}).get('visible'):
            print("\n[METHOD2] locator.click()")
            try:
                await page.locator("#edui41_state").click(timeout=5000)
                print("[METHOD2] clicked via locator.click()")
            except Exception as e:
                print(f"[METHOD2 error] {e}")
            await page.wait_for_timeout(2000)

            check2 = await page.evaluate("""() => {
                var e42 = document.getElementById('edui42');
                if (!e42) return null;
                var r = e42.getBoundingClientRect();
                return {display: getComputedStyle(e42).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (e42.innerText||'').trim().slice(0,300)};
            }""")
            result["check2"] = check2
            print(f"[CHECK2] edui42 display={check2.get('display')} visible={check2.get('visible')} rect={check2.get('rect')}")

        # ── 方法3：用 JS dispatch 完整 mouse sequence 到 body ──
        if not check1.get('edui42', {}).get('visible') and not (check2 and check2.get('visible')):
            print("\n[METHOD3] JS mouseover→mousemove→mousedown→mouseup→click")
            await page.evaluate("""(function() {
                var el = document.getElementById('edui41_state');
                if (!el) return;
                var r = el.getBoundingClientRect();
                var cx = r.x + r.width/2, cy = r.y + r.height/2;
                var send = function(type, button, buttons) {
                    var evt = new MouseEvent(type, {
                        bubbles: true, cancelable: true, view: window,
                        clientX: cx, clientY: cy, button: button||0,
                        buttons: buttons||0, which: 1, detail: 1
                    });
                    el.dispatchEvent(evt);
                };
                send('mouseover');
                send('mousemove');
                send('mousedown', 0, 1);
                send('mouseup', 0, 0);
                send('click', 0, 0);
            })()""")
            await page.wait_for_timeout(2000)

            check3 = await page.evaluate("""() => {
                var e42 = document.getElementById('edui42');
                if (!e42) return null;
                var r = e42.getBoundingClientRect();
                return {display: getComputedStyle(e42).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (e42.innerText||'').trim().slice(0,300), html: e42.innerHTML.slice(0,500)};
            }""")
            result["check3"] = check3
            print(f"[CHECK3] edui42 display={check3.get('display')} visible={check3.get('visible')} rect={check3.get('rect')}")
            print(f"[CHECK3] text={repr(check3.get('text','')[:200])}")

        # ── 最终：找 file input ──────────────────────────
        final = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type=file]')).map(function(el) {
                return {
                    accept: el.accept,
                    hidden: el.hidden || el.style.display === 'none',
                    visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                    rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                };
            });
        }""")
        result["final"] = final
        print(f"\n[FINAL] file_inputs={len(final)}")
        for fi in final:
            print(f"  accept={fi['accept']!r} visible={fi['visible']} rect={fi['rect']}")

        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_v9.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
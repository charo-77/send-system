"""
debug_insert_v6.py
用 page.evaluate 直接探测 + 触发插入下拉菜单（CDP 有问题，用 Playwright 原生）
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v6"
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
        result["steps"].append({"step": "editor_ready"})
        print("[PAGE] editor ready")

        # ── 1. 探查当前 DOM 状态 ─────────────────────────────
        initial = await page.evaluate("""() => {
            return {
                edui41: (() => {
                    var el = document.getElementById('edui41');
                    if (!el) return null;
                    var r = el.getBoundingClientRect();
                    return {id: el.id, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: el.innerText.trim(), cls: el.className.toString().slice(0,80)};
                })(),
                edui41_state: (() => {
                    var el = document.getElementById('edui41_state');
                    if (!el) return null;
                    var r = el.getBoundingClientRect();
                    return {id: el.id, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: el.innerText.trim(), cls: el.className.toString().slice(0,80), onmousedown: el.getAttribute('onmousedown'), onclick: el.getAttribute('onclick')};
                })(),
                edui42: (() => {
                    var el = document.getElementById('edui42');
                    if (!el) return null;
                    var r = el.getBoundingClientRect();
                    return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,300)};
                })(),
                editorui_v2_keys: typeof $EDITORUI_V2 !== 'undefined' ? Object.keys($EDITORUI_V2) : [],
                has_ue_v2: typeof UE_V2 !== 'undefined',
            };
        }""")
        result["initial"] = initial
        print(f"[INITIAL] edui41_state={initial.get('edui41_state')} onmousedown={initial.get('edui41_state',{}).get('onmousedown')}")
        print(f"[INITIAL] editorui_v2_keys={initial.get('editorui_v2_keys', [])[:10]}")
        print(f"[INITIAL] edui42 display={initial.get('edui42',{}).get('display')} visible={initial.get('edui42',{}).get('visible')}")

        # ── 2. 直接触发 edui41_state 的 onmousedown ──────────
        # onmousedown="$EDITORUI_V2[\"edui41\"].Stateful_onMouseDown(event, this);"
        # 这里的 JS 代码引用了 $EDITORUI_V2 全局变量
        js_code = initial.get('edui41_state', {}).get('onmousedown', '')
        print(f"\n[ONMOUSEDOWN JS] {js_code}")
        result["onmousedown_js"] = js_code

        # 执行原始的 onmousedown 属性
        if js_code:
            try:
                await page.evaluate(f"""(function(){{
                    var el = document.getElementById('edui41_state');
                    if (el) {{ el.dispatchEvent(new MouseEvent('mousedown', {{bubbles:true,cancelable:true,view:window,clientX:0,clientY:0,button:0}})); }}
                }})()""")
                print("[DISPATCH] dispatched mousedown via dispatchEvent")
            except Exception as e:
                print(f"[DISPATCH error] {e}")

        await page.wait_for_timeout(2000)

        check_a = await page.evaluate("""() => {
            var el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            var r = el.getBoundingClientRect();
            return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
        }""")
        result["check_a"] = check_a
        print(f"\n[CHECK_A after dispatchEvent] display={check_a.get('display')} visible={check_a.get('visible')} rect={check_a.get('rect')}")

        # ── 3. 方法2：直接在页面执行 onmousedown 属性的 JS ────
        if not check_a.get('visible'):
            print("\n[METHOD2] executing onmousedown JS code directly")
            exec_result = await page.evaluate("""(function() {
                var state_el = document.getElementById('edui41_state');
                if (!state_el) return 'no state_el';
                var jsCode = state_el.getAttribute('onmousedown');
                if (!jsCode) return 'no onmousedown';
                // eval the JS code with $EDITORUI_V2 in scope
                try {
                    eval(jsCode);
                    return 'evaled: ' + jsCode.slice(0,100);
                } catch(e) {
                    return 'eval error: ' + e.message;
                }
            })()""")
            print(f"[EXEC RESULT] {exec_result}")
            result["exec_result"] = exec_result
            await page.wait_for_timeout(2500)

            check_b = await page.evaluate("""() => {
                var el = document.getElementById('edui42');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
            }""")
            result["check_b"] = check_b
            print(f"[CHECK_B] display={check_b.get('display')} visible={check_b.get('visible')}")

        # ── 4. 方法3：Playwright 真实 mouse click ────────────
        if not check_a.get('visible') and not (check_b and check_b.get('visible')):
            print("\n[METHOD3] Playwright click edui41_state")
            state_rect = await page.evaluate("""() => {
                var el = document.getElementById('edui41_state');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: el.innerText.trim()};
            }""")
            if state_rect:
                print(f"[PW CLICK] moving to ({state_rect['cx']}, {state_rect['cy']}) text={state_rect['text']}")
                await page.mouse.move(state_rect['cx'], state_rect['cy'])
                await page.wait_for_timeout(500)
                await page.mouse.click(state_rect['cx'], state_rect['cy'])
                await page.wait_for_timeout(2500)

            check_c = await page.evaluate("""() => {
                var el = document.getElementById('edui42');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
            }""")
            result["check_c"] = check_c
            print(f"[CHECK_C] display={check_c.get('display')} visible={check_c.get('visible')}")

        # ── 5. 方法4：使用 Function 构造执行 onmousedown ─────
        if not check_a.get('visible') and not (check_b and check_b.get('visible')) and not (check_c and check_c.get('visible')):
            print("\n[METHOD4] call onmousedown via Function")
            await page.evaluate("""(function() {
                var el = document.getElementById('edui41_state');
                if (!el) return;
                var jsCode = el.getAttribute('onmousedown');
                if (!jsCode) return;
                // Replace the $EDITORUI_V2 reference with window.$EDITORUI_V2
                var fn = new Function('event', 'this', jsCode.replace(/\\$\\$EDITORUI_V2/g, 'window.$EDITORUI_V2'));
                var evt = new MouseEvent('mousedown', {bubbles:true,cancelable:true,view:window,clientX:0,clientY:0,button:0,buttons:0});
                fn.call(el, evt, el);
            })()""")
            await page.wait_for_timeout(2500)

            check_d = await page.evaluate("""() => {
                var el = document.getElementById('edui42');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
            }""")
            result["check_d"] = check_d
            print(f"[CHECK_D] display={check_d.get('display')} visible={check_d.get('visible')}")

        # ── 最终：所有 file input + visible popups ──────────
        final = await page.evaluate("""() => {
            var popups = Array.from(document.querySelectorAll('[class*=popup],[class*=drawer],[class*=dropdown],[class*=menu]'))
                .filter(function(el) {
                    var r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
                })
                .map(function(el) {
                    return {
                        id: el.id,
                        cls: el.className.toString().slice(0, 80),
                        rect: (function() { var r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                        text: (el.innerText || '').trim().slice(0, 200)
                    };
                });
            var fileInputs = Array.from(document.querySelectorAll('input[type=file]'))
                .map(function(el) {
                    return {
                        accept: el.accept,
                        hidden: el.hidden || el.style.display === 'none',
                        visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                        rect: (function() { var r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })()
                    };
                });
            return {popups: popups, fileInputs: fileInputs, body_snippet: (document.body.innerText || '').slice(0, 2000)};
        }""")
        result["final"] = final
        print(f"\n[FINAL] popups={final['popups'].length} fileInputs={final['fileInputs'].length}")
        for p in final['popups'][:10]:
            print(f"  [{p['id']}] rect={p['rect']} text={p['text'][:80]}")
        for fi in final['fileInputs']:
            print(f"  file: accept={fi['accept']} visible={fi['visible']} rect={fi['rect']}")

        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_v6.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
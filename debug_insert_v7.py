"""
debug_insert_v7.py
关键发现：
- $EDITORUI_V2 keys 是 ['edui1','edui2',...] 不是 ['edui41']
- Stateful_onMouseDown 在 prototype 上，需要正确的 event + context
- 直接 eval onmousedown JS 和 Playwright click 都失败
- 尝试用 CDP 原生 Input.dispatchMouseEvent 发送更底层的鼠标事件
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v7"
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

        # CDP session
        cdp = await context.new_cdp_session(page)

        # 探查当前状态
        state = await page.evaluate("""() => {
            var ins_keys = typeof $EDITORUI_V2 !== 'undefined' ? Object.keys($EDITORUI_V2) : [];
            var state_el = document.getElementById('edui41_state');
            var r = state_el ? state_el.getBoundingClientRect() : null;
            // 找 edui41 的实际 key
            var edui41_key = null;
            Object.keys($EDITORUI_V2).forEach(function(k) {
                var v = $EDITORUI_V2[k];
                if (v && v.__proto__ && v.__proto__.constructor && v.__proto__.constructor.name && v.__proto__.constructor.name.includes('Stateful')) {
                    edui41_key = k;
                }
            });
            return {
                ins_keys: ins_keys.slice(0, 20),
                edui41_key: edui41_key,
                state_rect: r ? {cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: state_el.innerText.trim()} : null,
                edui42_display: (function() { var e=document.getElementById('edui42'); return e ? getComputedStyle(e).display : null; })(),
                // 找所有有 onmousedown 的元素
                mousedown_elements: Array.from(document.querySelectorAll('[onmousedown]')).map(function(el) {
                    return {id: el.id, cls: el.className.toString().slice(0,60), onmousedown: el.getAttribute('onmousedown').slice(0,100), text: el.innerText.trim().slice(0,50)};
                }),
            };
        }""")
        result["initial"] = state
        print(f"[STATE] ins_keys={state.get('ins_keys')}")
        print(f"[STATE] edui41_key={state.get('edui41_key')}")
        print(f"[STATE] state_rect={state.get('state_rect')}")
        print(f"[STATE] edui42_display={state.get('edui42_display')}")
        print(f"[STATE] mousedown_elements count={len(state.get('mousedown_elements', []))}")
        for me in state.get('mousedown_elements', [])[:5]:
            print(f"  [{me['id']}] onmousedown={me['onmousedown']}")

        cx = state['state_rect']['cx']
        cy = state['state_rect']['cy']

        # ── 方法1：CDP Input.dispatchMouseEvent 发送完整鼠标序列 ─
        print(f"\n[METHOD1 CDP] dispatching to ({cx}, {cy})")

        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": cx, "y": cy, "button": "none", "clickCount": 0})
        await asyncio.sleep(0.3)
        await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": cx, "y": cy, "button": "left", "clickCount": 1})
        await asyncio.sleep(0.15)
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1})
        result["steps"].append({"step": "cdp_mouse", "cx": cx, "cy": cy})
        print("[METHOD1] dispatched CDP mouse events")
        await page.wait_for_timeout(2500)

        check1 = await page.evaluate("""() => {
            var el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            var r = el.getBoundingClientRect();
            return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
        }""")
        result["check1"] = check1
        print(f"[CHECK1 CDP] display={check1.get('display')} visible={check1.get('visible')}")

        # ── 方法2：找正确的 edui 实例 key 并直接调用 ───────────
        if not check1.get('visible'):
            print("\n[METHOD2] call via correct key + prototype")
            method2_result = await page.evaluate("""(function() {
                // 找包含 Stateful 方法的实例
                var targetKey = null;
                var targetIns = null;
                Object.keys($EDITORUI_V2).forEach(function(k) {
                    var v = $EDITORUI_V2[k];
                    if (v && v.__proto__ && typeof v.__proto__['Stateful_onMouseDown'] === 'function') {
                        targetKey = k;
                        targetIns = v;
                    }
                });

                var state_el = document.getElementById('edui41_state');
                if (!targetIns || !state_el) return {error: 'missing', targetKey: targetKey};

                var proto = targetIns.__proto__;
                var r = state_el.getBoundingClientRect();
                var cx = r.x + r.width/2, cy = r.y + r.height/2;

                // 构造完整的 MouseEvent
                var mouseEvent = new MouseEvent('mousedown', {
                    bubbles: true, cancelable: true, view: window,
                    clientX: cx, clientY: cy,
                    button: 0, buttons: 1,
                    which: 1, detail: 1
                });

                // 调用 prototype 上的 Stateful_onMouseDown 和 Stateful_onMouseUp
                proto['Stateful_onMouseDown'].call(targetIns, mouseEvent, state_el);

                var mouseEventUp = new MouseEvent('mouseup', {
                    bubbles: true, cancelable: true, view: window,
                    clientX: cx, clientY: cy,
                    button: 0, buttons: 0, which: 1, detail: 1
                });
                proto['Stateful_onMouseUp'].call(targetIns, mouseEventUp, state_el);

                return {called: true, targetKey: targetKey, proto_methods: Object.keys(proto).filter(function(k){return typeof proto[k]==='function';})};
            })()""")
            print(f"[METHOD2 RESULT] {json.dumps(method2_result, ensure_ascii=False)}")
            result["method2_result"] = method2_result
            await page.wait_for_timeout(2500)

            check2 = await page.evaluate("""() => {
                var el = document.getElementById('edui42');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300), html: el.innerHTML.slice(0,500)};
            }""")
            result["check2"] = check2
            print(f"[CHECK2] display={check2.get('display')} visible={check2.get('visible')}")

        # ── 方法3：直接 eval onmousedown 属性（修复 Function 参数）──
        if not check1.get('visible') and not (check2 and check2.get('visible')):
            print("\n[METHOD3] eval onmousedown")
            method3 = await page.evaluate("""(function() {
                var state_el = document.getElementById('edui41_state');
                if (!state_el) return 'no state_el';
                var jsCode = state_el.getAttribute('onmousedown');
                if (!jsCode) return 'no onmousedown';
                // 直接用 eval，因为 $EDITORUI_V2 是全局变量
                var result;
                try {
                    // 构建一个包含 $EDITORUI_V2 引用的函数
                    var fn = new Function('eventArg', 'thisArg', 'var event=eventArg; var self=thisArg; ' + jsCode);
                    var evt = new MouseEvent('mousedown', {bubbles:true,cancelable:true,view:window,clientX:0,clientY:0,button:0,buttons:0});
                    fn.call(state_el, evt, state_el);
                    result = 'evaled ok';
                } catch(e) {
                    result = 'error: ' + e.message;
                }
                return result;
            })()""")
            print(f"[METHOD3] {method3}")
            result["method3"] = method3
            await page.wait_for_timeout(2500)

            check3 = await page.evaluate("""() => {
                var el = document.getElementById('edui42');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,300)};
            }""")
            result["check3"] = check3
            print(f"[CHECK3] display={check3.get('display')} visible={check3.get('visible')}")

        # ── 最终检查：所有 popup + file input ─────────────────
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
            return {popups: popups, fileInputs: fileInputs};
        }""")
        result["final"] = final
        print(f"\n[FINAL] popups={len(final['popups'])} fileInputs={len(final['fileInputs'])}")
        for p in final['popups'][:10]:
            print(f"  [{p['id']}] rect={p['rect']} text={p['text'][:80]}")
        for fi in final['fileInputs']:
            print(f"  file: accept={fi['accept']} visible={fi['visible']} rect={fi['rect']}")

        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_v7.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
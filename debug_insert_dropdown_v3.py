"""
debug_insert_dropdown_v3.py
关键发现：
1. edui41_state (slot-inner-box) 上有 onmousedown="$EDITORUI_V2[\"edui41\"].Stateful_onMouseDown(event, this);"
2. edui41 实例只有 ['_Stateful_dGetHtmlTpl', 'getHtmlTpl']，没有 Stateful_onMouseDown
3. edui42 是隐藏的 iframe-popup，需要找触发显示的方法

目标：找到触发「插入」下拉菜单的正确方式
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_dropdown_v3"
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
        result["steps"].append({"step": "goto", "url": page.url})

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
        result["steps"].append({"step": "editor_ready"})

        # ── 探测所有 edui 实例的方法 ───────────────────────
        all_methods = await page.evaluate("""() => {
            const results = {};
            if (typeof $EDITORUI_V2 !== 'undefined') {
                Object.keys($EDITORUI_V2).forEach(k => {
                    const v = $EDITORUI_V2[k];
                    if (v && typeof v === 'object') {
                        const methods = Object.keys(v).filter(m => typeof v[m] === 'function');
                        if (methods.length > 0) {
                            results[k] = methods.slice(0, 50);
                        }
                    }
                });
            }
            return results;
        }""")
        result["all_methods"] = all_methods
        print(f"[ALL METHODS] keys={list(all_methods.keys())[:20]}")
        for k, methods in list(all_methods.items())[:10]:
            print(f"  {k}: {methods}")

        # ── 找 edui41 相关的所有实例和关系 ──────────────────
        edui41_deps = await page.evaluate("""() => {
            const ins = $EDITORUI_V2 && $EDITORUI_V2['edui41'];
            const state_el = document.getElementById('edui41_state');
            const state_el_ins = state_el ? $EDITORUI_V2 && $EDITORUI_V2['edui41_state'] : null;

            return {
                edui41_keys: ins ? Object.keys(ins) : [],
                edui41_state_onmousedown: state_el ? state_el.getAttribute('onmousedown') : null,
                edui41_state_onmouseup: state_el ? state_el.getAttribute('onmouseup') : null,
                edui41_state_onmouseover: state_el ? state_el.getAttribute('onmouseover') : null,
                edui41_state_onmouseout: state_el ? state_el.getAttribute('onmouseout') : null,
                edui41_state_inyerhtml: state_el ? state_el.outerHTML.slice(0, 500) : null,
                // edui41_state 实例
                edui41_state_ins_keys: state_el_ins ? Object.keys(state_el_ins) : [],
                edui41_state_ins_methods: state_el_ins ? Object.keys(state_el_ins).filter(k => typeof state_el_ins[k] === 'function') : [],
            };
        }""")
        result["edui41_deps"] = edui41_deps
        print(f"\n[EDUI41 DEPS]")
        print(f"  edui41_keys={edui41_deps.get('edui41_keys')}")
        print(f"  edui41_state_onmousedown={edui41_deps.get('edui41_state_onmousedown')}")
        print(f"  edui41_state_ins_keys={edui41_deps.get('edui41_state_ins_keys')}")
        print(f"  edui41_state_ins_methods={edui41_deps.get('edui41_state_ins_methods')}")

        # ── 核心调用：在 edui41_state 上触发 Stateful_onMouseDown ──
        # onmousedown="$EDITORUI_V2[\"edui41\"].Stateful_onMouseDown(event, this)"
        # 这里的 this = edui41_state 元素本身
        call_v1 = await page.evaluate("""() => {
            const state_el = document.getElementById('edui41_state');
            if (!state_el) return {error: 'no edui41_state'};
            const ins = $EDITORUI_V2 && $EDITORUI_V2['edui41'];
            if (!ins) return {error: 'no edui41 instance'};

            // 检查 edui41 实例里 Stateful_onMouseDown 是否实际存在（可能在原型链）
            const hasSM = typeof (ins['Stateful_onMouseDown'] || (ins.constructor && ins.constructor.prototype && ins.constructor.prototype['Stateful_onMouseDown']));
            const protoMethods = ins.__proto__ ? Object.keys(ins.__proto__) : [];
            const ctorMethods = ins.constructor ? Object.keys(ins.constructor.prototype) : [];

            const r = state_el.getBoundingClientRect();
            const evt = new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window, clientX: r.x + r.width/2, clientY: r.y + r.height/2, button: 0, buttons: 1 });

            // 直接执行 onmousedown 属性里的 JS
            const jsCode = state_el.getAttribute('onmousedown');
            let result = null;
            if (jsCode) {
                try {
                    // 构建一个 fake event 和正确的 this
                    const fakeEvent = evt;
                    const fakeThis = state_el;
                    // 用 Function 构造执行
                    const fn = new Function('event', 'this', jsCode.replace('event', 'event').replace(/\$\_EDITORUI\_V2/g, 'window.$EDITORUI_V2'));
                    fn.call(state_el, fakeEvent, state_el);
                    result = 'executed JS: ' + jsCode.slice(0, 100);
                } catch(e) {
                    result = 'error: ' + e.message;
                }
            } else {
                result = 'no onmousedown attr';
            }

            return { result, jsCode: jsCode ? jsCode.slice(0, 100) : null, hasSM, protoMethods: protoMethods.slice(0, 20), ctorMethods: ctorMethods.slice(0, 20) };
        }""")
        print(f"\n[CALL V1 onmousedown attr] {call_v1}")
        result["call_v1"] = call_v1
        await page.wait_for_timeout(2500)

        # ── 检查 edui42 是否显示了 ─────────────────────────
        check1 = await page.evaluate("""() => {
            const el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            const r = el.getBoundingClientRect();
            const visible = r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
            return {
                display: getComputedStyle(el).display,
                visible,
                rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                html: el.innerHTML.slice(0, 300),
                // 检查 iframe 的 src
                iframe_src: (() => { const iframe = el.querySelector('iframe'); return iframe ? iframe.src : null; })(),
            };
        }""")
        result["check1"] = check1
        print(f"\n[CHECK1 edui42] display={check1.get('display')} visible={check1.get('visible')} rect={check1.get('rect')}")
        if check1.get('visible'):
            print(f"  edui42 iframe_src={check1.get('iframe_src')}")

        # ── 方法2：Playwright 直接 click edui41_state ────────
        state_rect = await page.evaluate("""() => {
            const el = document.getElementById('edui41_state');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {cx: r.x + r.width/2, cy: r.y + r.height/2, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: el.innerText.trim()};
        }""")
        if state_rect:
            print(f"\n[PLAYWRIGHT CLICK edui41_state] rect={state_rect}")
            await page.mouse.move(state_rect['cx'], state_rect['cy'])
            await page.wait_for_timeout(500)
            await page.mouse.down()
            await page.wait_for_timeout(200)
            await page.mouse.up()
            await page.wait_for_timeout(2000)

        # ── 检查结果 ──────────────────────────────────────
        check2 = await page.evaluate("""() => {
            const checkEl = (el) => {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    display: getComputedStyle(el).display,
                    visible: r.width > 0 && r.height > 0,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 300),
                    html: el.outerHTML.slice(0, 500),
                };
            };
            return {
                edui42: checkEl(document.getElementById('edui42')),
                // 找所有可能新出现的菜单元素
                new_menus: Array.from(document.querySelectorAll('[class*="menu"], [class*="popup"], [class*="drawer"], [class*="dropdown"]'))
                    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
                    .map(el => ({ id: el.id, cls: (el.className && el.className.baseVal ? el.className.baseVal : (el.className||'')).toString().slice(0,80), rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(), text: (el.innerText||'').trim().slice(0,200) })),
                body_text: (document.body.innerText||'').slice(0, 2000),
            };
        }""")
        result["check2"] = check2
        print(f"\n[CHECK2 edui42] display={check2.get('edui42',{}).get('display')} visible={check2.get('edui42',{}).get('visible')} rect={check2.get('edui42',{}).get('rect')}")
        print(f"[CHECK2 new_menus] count={len(check2.get('new_menus', []))}")
        for m in check2.get('new_menus', [])[:10]:
            print(f"  [{m['id']}] rect={m['rect']} text={repr(m['text'][:80])}")

        # ── 方法3：找插入下拉菜单的真正入口 ────────────────────
        # 在 ueditor iframe 里找 toolbar 上的"插入"按钮 click handler
        # 百家号的 toolbar 是 React 组件，通过 onClick 触发
        find_insert_handler = await page.evaluate("""() => {
            const results = {};
            // 检查 toolbar 上的 click 事件绑定
            const edui41_el = document.getElementById('edui41');
            const edui41_state = document.getElementById('edui41_state');
            if (edui41_state) {
                // 查看元素上实际绑定的事件（通过 getEventListeners）
                if (window.getEventListeners) {
                    results['state_listeners'] = window.getEventListeners(edui41_state);
                }
                // 查看 jQuery 绑定的事件
                if (typeof jQuery !== 'undefined') {
                    const events = jQuery._data(edui41_state, 'events');
                    results['jquery_events'] = events;
                }
            }
            // 在 iframe 里查找
            const iframe = document.getElementById('ueditor_0');
            if (iframe && iframe.contentWindow) {
                const iwin = iframe.contentWindow;
                results['iframe_has_editorui_v2'] = typeof (iwin.$EDITORUI_V2 || iwin.UE_V2) !== 'undefined';
                results['iframe_editor_methods'] = iwin.UE_V2 && iwin.UE_V2.instants ? Object.keys(iwin.UE_V2.instants) : [];
                if (iwin.$EDITORUI_V2) {
                    const ins = iwin.$EDITORUI_V2['edui41'];
                    if (ins) {
                        results['iframe_edui41_methods'] = Object.keys(ins).filter(k => typeof ins[k] === 'function');
                    }
                }
            }
            return results;
        }""")
        result["find_insert_handler"] = find_insert_handler
        print(f"\n[FIND INSERT HANDLER] {json.dumps(find_insert_handler, ensure_ascii=False)[:600]}")

        # ── 截图 ───────────────────────────────────────────
        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_trigger_v3.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
"""
debug_insert_dropdown_v4.py
关键发现：
- Stateful_onMouseDown 在 prototype 上，不是实例直接方法
- Stateful_onMouseUp 是触发 popup 的关键
- 需要从 prototype 调用 Stateful_onMouseDown/Up
目标：找到正确触发「插入」下拉菜单的方式
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_dropdown_v4"
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

        # ── 从 prototype 调用 Stateful 方法 ─────────────────
        # edui41 实例的 __proto__ 是 Stateful prototype，上面有 Stateful_onMouseDown/Up
        call_proto = await page.evaluate("""() => {
            const ins = $EDITORUI_V2 && $EDITORUI_V2['edui41'];
            if (!ins) return {error: 'no edui41'};

            const state_el = document.getElementById('edui41_state');
            if (!state_el) return {error: 'no edui41_state'};

            // 从 __proto__ 找 Stateful 方法
            const proto = ins.__proto__;
            const methods_on_proto = proto ? Object.keys(proto).filter(k => typeof proto[k] === 'function') : [];
            const stateful_methods = methods_on_proto.filter(k => k.startsWith('Stateful_'));

            // 构建 MouseEvent
            const r = state_el.getBoundingClientRect();
            const mouseEvent = new MouseEvent('mousedown', {
                bubbles: true, cancelable: true, view: window,
                clientX: r.x + r.width / 2, clientY: r.y + r.height / 2,
                button: 0, buttons: 1
            });
            const mouseEventUp = new MouseEvent('mouseup', {
                bubbles: true, cancelable: true, view: window,
                clientX: r.x + r.width / 2, clientY: r.y + r.height / 2,
                button: 0, buttons: 0
            });

            // 调用 Stateful_onMouseDown 和 Stateful_onMouseUp
            let down_result = null, up_result = null;
            if (proto && typeof proto['Stateful_onMouseDown'] === 'function') {
                try {
                    proto['Stateful_onMouseDown'].call(ins, mouseEvent, state_el);
                    down_result = 'called Stateful_onMouseDown from proto';
                } catch(e) {
                    down_result = 'err: ' + e.message;
                }
            }
            setTimeout(function(){}, 500);
            if (proto && typeof proto['Stateful_onMouseUp'] === 'function') {
                try {
                    proto['Stateful_onMouseUp'].call(ins, mouseEventUp, state_el);
                    up_result = 'called Stateful_onMouseUp from proto';
                } catch(e) {
                    up_result = 'err: ' + e.message;
                }
            }

            return {
                proto_methods: methods_on_proto.slice(0, 30),
                stateful_methods,
                down_result,
                up_result,
                ins_keys: Object.keys(ins),
            };
        }""")
        print(f"\n[CALL PROTO] {json.dumps(call_proto, ensure_ascii=False, indent=2)}")
        result["call_proto"] = call_proto
        await page.wait_for_timeout(2500)

        # ── 检查结果 ────────────────────────────────────────
        check1 = await page.evaluate("""() => {
            const el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            const r = el.getBoundingClientRect();
            return {
                display: getComputedStyle(el).display,
                visible: r.width > 0 && r.height > 0,
                rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                text: (el.innerText||'').trim().slice(0, 300),
                html: el.outerHTML.slice(0, 500),
            };
        }""")
        result["check1"] = check1
        print(f"\n[CHECK1 edui42] display={check1.get('display')} visible={check1.get('visible')}")
        print(f"  text={repr(check1.get('text','')[:200])}")

        # ── 方法2：Playwright 直接 click edui41_state (模拟真实用户点击) ──
        state_rect = await page.evaluate("""() => {
            const el = document.getElementById('edui41_state');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {cx: r.x + r.width/2, cy: r.y + r.height/2, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
        }""")
        if state_rect:
            print(f"\n[PW CLICK edui41_state] center=({state_rect['cx']}, {state_rect['cy']})")
            await page.mouse.move(state_rect['cx'], state_rect['cy'])
            await page.wait_for_timeout(300)
            await page.mouse.click(state_rect['cx'], state_rect['cy'], delay=100)
            await page.wait_for_timeout(2500)

        check2 = await page.evaluate("""() => {
            const checkEl = (id) => {
                const el = document.getElementById(id);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    display: getComputedStyle(el).display,
                    visible: r.width > 0 && r.height > 0,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 300),
                    html: el.outerHTML.slice(0, 800),
                };
            };
            const popups = Array.from(document.querySelectorAll('[class*="popup"], [class*="drawer"], [class*="dropdown"], [class*="menu"]'))
                .filter(el => { const r=el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
                .map(el => ({
                    id: el.id,
                    cls: (el.className && el.className.baseVal ? el.className.baseVal : (el.className||'')).toString().slice(0,80),
                    rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                    text: (el.innerText||'').trim().slice(0,200)
                }));
            return {
                edui42: checkEl('edui42'),
                popups,
                body_text: (document.body.innerText||'').slice(0, 2000),
            };
        }""")
        result["check2"] = check2
        print(f"\n[CHECK2 edui42] display={check2.get('edui42',{}).get('display')} visible={check2.get('edui42',{}).get('visible')}")
        print(f"[CHECK2 popups] count={len(check2.get('popups',[]))}")
        for m in check2.get('popups',[])[:10]:
            print(f"  [{m['id']}] rect={m['rect']} text={repr(m['text'][:80])}")
        if check2.get('edui42', {}).get('visible'):
            print(f"  EDUI42 VISIBLE! html={check2['edui42']['html'][:300]}")

        # ── 方法3：用 edui41 实例直接 .click() ───────────────
        click_result = await page.evaluate("""() => {
            const ins = $EDITORUI_V2 && $EDITORUI_V2['edui41'];
            const state_el = document.getElementById('edui41_state');
            if (!ins || !state_el) return {error: 'missing'};

            // 尝试调用 onclick 方法（如果有的话）
            if (typeof ins['onclick'] === 'function') {
                try { ins['onclick'](); return 'called onclick'; } catch(e) { return 'onclick err: ' + e.message; }
            }
            // 尝试调用 $EDITORUI_V2["edui41"].Stateful_onMouseDown 通过 prototype
            const proto = ins.__proto__;
            if (proto && typeof proto['Stateful_onMouseDown'] === 'function') {
                const r = state_el.getBoundingClientRect();
                const evt = new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window, clientX: r.x+r.width/2, clientY: r.y+r.height/2, button: 0, buttons: 1 });
                const evtUp = new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window, clientX: r.x+r.width/2, clientY: r.y+r.height/2, button: 0, buttons: 0 });
                try { proto['Stateful_onMouseDown'].call(ins, evt, state_el); } catch(e) { return 'down err: ' + e.message; }
                try { proto['Stateful_onMouseUp'].call(ins, evtUp, state_el); } catch(e) { return 'up err: ' + e.message; }
                return 'called proto Stateful methods';
            }
            return 'no proto or methods found';
        }""")
        print(f"\n[CLICK RESULT] {click_result}")
        result["click_result"] = click_result
        await page.wait_for_timeout(2500)

        check3 = await page.evaluate("""() => {
            const el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            const r = el.getBoundingClientRect();
            return {
                display: getComputedStyle(el).display,
                visible: r.width > 0 && r.height > 0,
                rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                text: (el.innerText||'').trim().slice(0, 300),
            };
        }""")
        result["check3"] = check3
        print(f"\n[CHECK3 edui42] display={check3.get('display')} visible={check3.get('visible')} rect={check3.get('rect')}")

        # ── 截图 ───────────────────────────────────────────
        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_trigger_v4.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
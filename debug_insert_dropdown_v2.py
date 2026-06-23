"""
debug_insert_dropdown_v2.py
目标：找到触发「插入」下拉菜单的正确 JS 路径，重点是找到 edui41 onclick 处理的调用方式。
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_dropdown_v2"
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

        # ── 详细探测 edui41 结构 ─────────────────────────
        edui41_probe = await page.evaluate("""() => {
            const el = document.getElementById('edui41');
            if (!el) return {error: 'edui41 not found'};
            const ins = $EDITORUI_V2 && $EDITORUI_V2['edui41'];
            const r = el.getBoundingClientRect();
            const cx = r.x + r.width/2, cy = r.y + r.height/2;

            // 从 onmousedown handler 看，它用的是 $EDITORUI_V2["edui41"]._onMouseDown(event, this)
            // this 是什么？应该是 el (edui41本身) 或其子元素
            // 先找到 onclick 属性
            const onclick_attr = el.getAttribute('onclick');
            const onmousedown_attr = el.getAttribute('onmousedown');

            // 找子元素里的 onclick
            const children = Array.from(el.querySelectorAll('*')).slice(0, 10).map(child => ({
                tag: child.tagName,
                id: child.id,
                cls: (child.className && child.className.baseVal ? child.className.baseVal : (child.className || '')).toString().slice(0, 60),
                onclick: child.getAttribute('onclick'),
                onmousedown: child.getAttribute('onmousedown'),
                innerText: (child.innerText || '').trim().slice(0, 50),
            }));

            return {
                rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                onclick: onclick_attr,
                onmousedown: onmousedown_attr,
                children,
                // $EDITORUI_V2["edui41"] 的所有属性和方法
                ins_methods: ins ? Object.keys(ins).filter(k => typeof ins[k] === 'function').slice(0, 40) : [],
                // _onMouseDown 的签名
                _onMouseDown_type: typeof (ins && ins._onMouseDown),
                _onMouseDown_params: ins && ins._onMouseDown ? ins._onMouseDown.toString().slice(0, 200) : null,
                // getHtmlTpl 返回什么
                getHtmlTpl_result: ins && typeof ins.getHtmlTpl === 'function' ? ins.getHtmlTpl() : null,
                // 找 slot-inner-box 的 onclick
                slot_inner: (() => {
                    const slot = el.querySelector('.slot-inner-box, [class*="slot-inner"]');
                    return slot ? {
                        onclick: slot.getAttribute('onclick'),
                        onmousedown: slot.getAttribute('onmousedown'),
                    } : null;
                })(),
            };
        }""")
        result["edui41_probe"] = edui41_probe
        print(f"[EDUI41 PROBE] onclick={edui41_probe.get('onclick')}")
        print(f"[EDUI41 PROBE] onmousedown={edui41_probe.get('onmousedown')}")
        print(f"[EDUI41 PROBE] children={json.dumps(edui41_probe.get('children'), ensure_ascii=False)[:500]}")
        print(f"[EDUI41 PROBE] ins_methods={edui41_probe.get('ins_methods', [])[:15]}")
        print(f"[EDUI41 PROBE] _onMouseDown_params={edui41_probe.get('_onMouseDown_params')}")
        print(f"[EDUI41 PROBE] slot_inner={edui41_probe.get('slot_inner')}")
        if edui41_probe.get('getHtmlTpl_result'):
            print(f"[EDUI41 PROBE] getHtmlTpl_result={str(edui41_probe['getHtmlTpl_result'])[:300]}")

        # ── 核心调用：_onMouseDown(event, el) ──────────────────
        # 正确的调用方式是：$EDITORUI_V2["edui41"]._onMouseDown(event_object, el)
        # event_object 需要是 MouseEvent，el 应该是 edui41 本身或其子元素
        call_result = await page.evaluate("""() => {
            const el = document.getElementById('edui41');
            if (!el) return {error: 'no edui41'};
            const ins = $EDITORUI_V2 && $EDITORUI_V2['edui41'];
            if (!ins) return {error: 'no instance'};

            const r = el.getBoundingClientRect();
            const cx = r.x + r.width/2, cy = r.y + r.height/2;

            // 构造一个真实的 MouseEvent
            const mouseEvent = new MouseEvent('click', {
                bubbles: true, cancelable: true, view: window,
                clientX: cx, clientY: cy, button: 0, buttons: 1
            });

            // 方式1: _onMouseDown(event, el) - 标准 edui 按钮调用方式
            let result1 = null;
            if (typeof ins._onMouseDown === 'function') {
                try {
                    ins._onMouseDown(mouseEvent, el);
                    result1 = 'called _onMouseDown(event, el)';
                } catch(e) {
                    result1 = 'err: ' + e.message;
                }
            } else {
                result1 = '_onMouseDown not found';
            }

            return {result1, el_id: el.id, el_tag: el.tagName};
        }""")
        print(f"\n[CALL _onMouseDown] {call_result}")
        result["call_result"] = call_result
        await page.wait_for_timeout(2500)

        # ── 检查 edui42 / 下拉菜单 ───────────────────────────
        popup_check = await page.evaluate("""() => {
            const check = (id) => {
                const el = document.getElementById(id);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const visible = r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
                return {
                    display: getComputedStyle(el).display,
                    visible,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 500),
                    html: el.outerHTML.slice(0, 1000),
                };
            };
            return {
                edui41_display: getComputedStyle(document.getElementById('edui41') || document.createElement('div')).display,
                edui42: check('edui42'),
                edui43: check('edui43'),
                // 查所有可见的 popup 类元素
                popup_els: Array.from(document.querySelectorAll('[class*="popup"], [class*="drawer"], [class*="dropdown"]'))
                    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
                    .map(el => ({ id: el.id, cls: (el.className && el.className.baseVal ? el.className.baseVal : (el.className || '')).toString().slice(0, 80), rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(), text: (el.innerText||'').trim().slice(0,200) })),
            };
        }""")
        result["popup_check"] = popup_check
        print(f"\n[POPUP CHECK] edui42 display={popup_check.get('edui42', {}).get('display')} visible={popup_check.get('edui42', {}).get('visible')}")
        print(f"[POPUP CHECK] popup_els count={len(popup_check.get('popup_els', []))}")
        for p in popup_check.get('popup_els', [])[:10]:
            print(f"  {p['id']} cls={p['cls'][:60]} rect={p['rect']} text={repr(p['text'][:80])}")
        if popup_check.get('edui42', {}).get('html'):
            print(f"  edui42 html={popup_check['edui42']['html'][:400]}")

        # ── 方式2：用 Playwright 的真实 click 触发 ──────────
        # 先用 page.mouse 移到 edui41 中心，再 click
        ui_state = await page.evaluate("""() => {
            const el = document.getElementById('edui41');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {cx: r.x + r.width/2, cy: r.y + r.height/2, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
        }""")
        if ui_state:
            print(f"\n[PLAYWRIGHT CLICK] moving to ({ui_state['cx']}, {ui_state['cy']})")
            await page.mouse.move(ui_state['cx'], ui_state['cy'])
            await page.wait_for_timeout(500)
            await page.mouse.click(ui_state['cx'], ui_state['cy'])
            await page.wait_for_timeout(2000)

        # 检查结果
        after_click = await page.evaluate("""() => {
            const check = (id) => {
                const el = document.getElementById(id);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    display: getComputedStyle(el).display,
                    visible: r.width > 0 && r.height > 0,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 500),
                    html: el.outerHTML.slice(0, 800),
                };
            };
            return {
                edui42: check('edui42'),
                edui43: check('edui43'),
                popup_els: Array.from(document.querySelectorAll('[class*="popup"], [class*="drawer"], [class*="dropdown"], [class*="insertion"]'))
                    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
                    .map(el => ({ id: el.id, cls: (el.className && el.className.baseVal ? el.className.baseVal : (el.className || '')).toString().slice(0, 80), rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(), text: (el.innerText||'').trim().slice(0,200) })),
            };
        }""")
        result["after_click"] = after_click
        print(f"\n[AFTER PW CLICK] edui42 display={after_click.get('edui42', {}).get('display')} visible={after_click.get('edui42', {}).get('visible')}")
        print(f"[AFTER PW CLICK] popup_els count={len(after_click.get('popup_els', []))}")
        for p in after_click.get('popup_els', [])[:10]:
            print(f"  {p['id']} cls={p['cls'][:60]} rect={p['rect']} text={repr(p['text'][:80])}")

        # ── 方式3：找 edui42.innerHTML 内容（它可能是隐藏iframe容器）──
        deep_check = await page.evaluate("""() => {
            const el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            const r = el.getBoundingClientRect();
            return {
                display: getComputedStyle(el).display,
                visible: r.width > 0 && r.height > 0,
                rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                innerHTML: el.innerHTML.slice(0, 2000),
                childCount: el.children.length,
                childTags: Array.from(el.children).map(c => c.tagName),
            };
        }""")
        result["deep_check"] = deep_check
        print(f"\n[DEEP CHECK edui42] display={deep_check.get('display')} innerHTML={deep_check.get('innerHTML', '')[:500]}")
        print(f"[DEEP CHECK edui42] childCount={deep_check.get('childCount')} childTags={deep_check.get('childTags')}")

        # ── 文件输入框扫描 ─────────────────────────────────
        file_scan = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type="file"]')).map(el => ({
                id: el.id, name: el.name, accept: el.accept,
                hidden: el.hidden || el.style.display === 'none',
                rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                html: el.outerHTML.slice(0, 300)
            }));
        }""")
        result["file_scan"] = file_scan
        print(f"\n[FILE SCAN] count={len(file_scan)}")
        for f in file_scan:
            print(f"  {f['html'][:200]}")

        # 截图
        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_trigger_v2.png"), full_page=True)
            result["steps"].append({"step": "screenshot", "path": str(DEBUG_DIR / "after_trigger_v2.png")})
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
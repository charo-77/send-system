"""
debug_insert_dropdown_v5.py
关键发现：
- Stateful_onMouseUp 在 prototype 上，需要 real mouseevent 触发
- edui42 是通过浏览器事件系统显示的，不是直接调用 JS 方法
- 百家号工具栏按钮使用 React 的合成事件系统，不是原生 addEventListener
目标：用 Playwright 模拟真实用户的完整 mouse sequence
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_dropdown_v5"
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
        await page.wait_for_timeout(2000)
        result["steps"].append({"step": "editor_ready"})

        # 获取 edui41_state 的 rect
        state_rect = await page.evaluate("""() => {
            const el = document.getElementById('edui41_state');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {cx: r.x + r.width/2, cy: r.y + r.height/2, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: (el.innerText||'').trim()};
        }""")
        print(f"[STATE RECT] {state_rect}")

        # ── 方法1：完整的真实 mouse sequence ──────────────────
        # 百家号工具栏按钮触发流程（从源码分析）：
        # 1. mouseover → Stateful_onMouseEnter (添加 hover state)
        # 2. mousemove
        # 3. mousedown → Stateful_onMouseDown (添加 pressed state)
        # 4. mouseup → Stateful_onMouseUp (弹出 popup) ← 这是关键！
        cx, cy = state_rect['cx'], state_rect['cy']

        print(f"[METHOD1] mouse sequence: over→move→down→up at ({cx},{cy})")
        await page.mouse.move(cx, cy)
        await page.wait_for_timeout(200)
        await page.mouse.down()  # mousedown
        await page.wait_for_timeout(100)
        await page.mouse.up()    # mouseup - should trigger popup
        await page.wait_for_timeout(2500)

        check1 = await page.evaluate("""() => {
            const el = document.getElementById('edui42');
            if (!el) return {error: 'no edui42'};
            const r = el.getBoundingClientRect();
            return {
                display: getComputedStyle(el).display,
                visible: r.width > 0 && r.height > 0,
                rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                text: (el.innerText||'').trim().slice(0, 300),
                html: el.innerHTML.slice(0, 500),
            };
        }""")
        result["check1"] = check1
        print(f"\n[CHECK1 edui42] display={check1.get('display')} visible={check1.get('visible')} rect={check1.get('rect')}")

        # ── 方法2：hover 后 click（不用 down/up） ──────────────
        if not check1.get('visible'):
            print("\n[METHOD2] hover then click")
            await page.mouse.move(cx, cy)
            await page.wait_for_timeout(500)
            await page.mouse.click(cx, cy)
            await page.wait_for_timeout(2500)

            check2 = await page.evaluate("""() => {
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
            result["check2"] = check2
            print(f"[CHECK2 edui42] display={check2.get('display')} visible={check2.get('visible')}")

        # ── 方法3：用 Playwright locator.click() ──────────────
        if not check1.get('visible') and not check2.get('visible'):
            print("\n[METHOD3] locator.click()")
            try:
                locator = page.locator('#edui41_state')
                await locator.click(click_count=2, delay=100)
            except Exception as e:
                print(f"[METHOD3 error] {e}")
            await page.wait_for_timeout(2500)

            check3 = await page.evaluate("""() => {
                const el = document.getElementById('edui42');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    display: getComputedStyle(el).display,
                    visible: r.width > 0 && r.height > 0,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 300),
                };
            }""")
            result["check3"] = check3
            print(f"[CHECK3 edui42] display={check3.get('display')} visible={check3.get('visible')}")

        # ── 方法4：直接 dispatchEvent 构造完整 MouseEvent ─────
        if not check1.get('visible') and not (check2 and check2.get('visible')) and not (check3 and check3.get('visible')):
            print("\n[METHOD4] dispatchEvent with full MouseEvent init")
            dispatch_result = await page.evaluate("""() => {
                const state_el = document.getElementById('edui41_state');
                if (!state_el) return 'no state_el';

                const r = state_el.getBoundingClientRect();
                const cx = r.x + r.width/2, cy = r.y + r.height/2;

                const types = ['mouseover', 'mousemove', 'mousedown', 'mouseup', 'click'];
                const results = {};

                types.forEach(type => {
                    const evt = new MouseEvent(type, {
                        bubbles: true, cancelable: true, view: window,
                        clientX: cx, clientY: cy,
                        button: 0, buttons: type === 'mousedown' ? 1 : 0,
                        detail: 1,
                        // 关键：UI events 需要这些
                        view: window,
                        which: 1,
                    });
                    try {
                        state_el.dispatchEvent(evt);
                        results[type] = 'dispatched';
                    } catch(e) {
                        results[type] = 'error: ' + e.message;
                    }
                });

                // 等一下让浏览器处理
                return results;
            }""")
            print(f"[DISPATCH RESULT] {dispatch_result}")
            result["dispatch_result"] = dispatch_result
            await page.wait_for_timeout(2500)

            check4 = await page.evaluate("""() => {
                const el = document.getElementById('edui42');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    display: getComputedStyle(el).display,
                    visible: r.width > 0 && r.height > 0,
                    rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 300),
                };
            }""")
            result["check4"] = check4
            print(f"[CHECK4 edui42] display={check4.get('display')} visible={check4.get('visible')}")

        # ── 最终检查：找所有可见的菜单/popup ──────────────────
        final_check = await page.evaluate("""() => {
            const popups = Array.from(document.querySelectorAll('*'))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 20 || r.height < 20) return false;
                    const display = getComputedStyle(el).display;
                    if (display === 'none' || display === 'none') return false;
                    const text = (el.innerText||'').trim();
                    return text.includes('插入') || text.includes('导入') || text.includes('文档') || text.includes('图片') || text.includes('视频');
                })
                .map(el => ({
                    id: el.id,
                    cls: (el.className && el.className.baseVal ? el.className.baseVal : (el.className||'')).toString().slice(0, 80),
                    rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                    text: (el.innerText||'').trim().slice(0, 200),
                }));
            return {popups, body_snippet: (document.body.innerText||'').slice(0, 3000)};
        }""")
        result["final_check"] = final_check
        print(f"\n[FINAL CHECK] found {len(final_check.get('popups', []))} relevant elements")
        for p in final_check.get('popups', [])[:10]:
            print(f"  [{p['id']}] rect={p['rect']} text={repr(p['text'][:80])}")

        # ── 文件输入框扫描 ─────────────────────────────────
        file_scan = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type="file"]')).map(el => ({
                accept: el.accept,
                hidden: el.hidden || el.style.display === 'none',
                rect: (() => { const r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
            }));
        }""")
        result["file_scan"] = file_scan
        print(f"\n[FILE SCAN] count={len(file_scan)}")
        for f in file_scan:
            print(f"  accept={f['accept']} hidden={f['hidden']} rect={f['rect']}")

        # ── 截图 ───────────────────────────────────────────
        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_trigger_v5.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
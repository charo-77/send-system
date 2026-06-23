"""
debug_insert_v11.py
probe2 发现的关键：hover edui41_state 后，edui42 变成 display:block
但需要 "hover edui41_state 区域" 之后，再 hover 到 edui42 区域，才会显示完整下拉菜单

两步 hover 方案：
Step1: mouse.move to edui41_state center → 触发 edui41 显示 "插入"
Step2: mouse.move to edui42 area → 显示下拉菜单
Step3: click "导入文档" 选项
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v11"
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
        print("[PAGE] editor ready")

        # 截图初始状态
        await page.screenshot(path=str(DEBUG_DIR / "step0_initial.png"), full_page=True)

        # 获取 edui41 和 edui42 的初始位置
        initial_rects = await page.evaluate("""() => {
            var e41 = document.getElementById('edui41');
            var e41_state = document.getElementById('edui41_state');
            var e42 = document.getElementById('edui42');
            var e42_content = document.getElementById('edui42_content');
            var getInfo = function(id) {
                var el = document.getElementById(id);
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, text: (el.innerText||'').trim().slice(0,200), html: el.outerHTML.slice(0,300)};
            };
            return {
                edui41: getInfo('edui41'),
                edui41_state: getInfo('edui41_state'),
                edui42: getInfo('edui42'),
                edui42_content: getInfo('edui42_content'),
            };
        }""")
        result["initial_rects"] = initial_rects
        print(f"[INITIAL] edui41={initial_rects.get('edui41')}")
        print(f"[INITIAL] edui41_state={initial_rects.get('edui41_state')}")
        print(f"[INITIAL] edui42 display={initial_rects.get('edui42',{}).get('display')} visible={initial_rects.get('edui42',{}).get('visible')}")

        # ── 步骤1：mouseover 触发 hover 状态 ─────────────────
        state_rect = initial_rects.get('edui41_state', {})
        cx1, cy1 = state_rect['cx'], state_rect['cy']
        print(f"\n[STEP1] mouse.move to edui41_state ({cx1}, {cy1})")

        # 先 mouseover 触发 React onmouseover
        await page.mouse.move(cx1, cy1)
        result["steps"].append({"step": "step1_hover", "x": cx1, "y": cy1})
        print("[STEP1] mouse moved, waiting 1.5s...")
        await page.wait_for_timeout(1500)

        # 截图 step1
        await page.screenshot(path=str(DEBUG_DIR / "step1_after_hover.png"), full_page=True)

        # 检查 hover 后状态
        after_step1 = await page.evaluate("""() => {
            var e41 = document.getElementById('edui41');
            var e42 = document.getElementById('edui42');
            var e42_content = document.getElementById('edui42_content');
            var getInfo = function(id) {
                var el = document.getElementById(id);
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {display: getComputedStyle(el).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (el.innerText||'').trim().slice(0,200), html: el.innerHTML.slice(0,300)};
            };
            return {edui41: getInfo('edui41'), edui42: getInfo('edui42'), edui42_content: getInfo('edui42_content')};
        }""")
        result["after_step1"] = after_step1
        print(f"\n[AFTER STEP1] edui41 text={after_step1.get('edui41',{}).get('text')} display={after_step1.get('edui41',{}).get('display')}")
        print(f"[AFTER STEP1] edui42 display={after_step1.get('edui42',{}).get('display')} visible={after_step1.get('edui42',{}).get('visible')} rect={after_step1.get('edui42',{}).get('rect')}")
        print(f"[AFTER STEP1] edui42_content display={after_step1.get('edui42_content',{}).get('display')} visible={after_step1.get('edui42_content',{}).get('visible')}")

        # ── 步骤2：如果 edui42 显示了，移动到 edui42 区域 ───
        e42_visible = after_step1.get('edui42', {}).get('visible') or after_step1.get('edui42', {}).get('display') == 'block'
        e42_rect = after_step1.get('edui42', {}).get('rect') or {}

        if e42_visible and e42_rect:
            cx2 = e42_rect.get('x', 0) + e42_rect.get('w', 0) // 2
            cy2 = e42_rect.get('y', 0) + e42_rect.get('h', 0) // 2
            print(f"\n[STEP2] edui42 is visible! moving to center ({cx2}, {cy2})")
            await page.mouse.move(cx2, cy2)
            result["steps"].append({"step": "step2_move_to_edui42", "x": cx2, "y": cy2})
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(DEBUG_DIR / "step2_after_edui42_hover.png"), full_page=True)

            # 检查 edui42_content 和下拉菜单
            after_step2 = await page.evaluate("""() => {
                var e42_content = document.getElementById('edui42_content');
                // 找 edui43（应该是下拉菜单项容器）
                var all_eduis = {};
                for (var i = 40; i <= 60; i++) {
                    var el = document.getElementById('edui' + i);
                    if (el) {
                        var r = el.getBoundingClientRect();
                        all_eduis['edui' + i] = {
                            display: getComputedStyle(el).display,
                            visible: r.width>0&&r.height>0,
                            rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                            text: (el.innerText||'').trim().slice(0,200),
                            html: el.innerHTML.slice(0, 400)
                        };
                    }
                }
                // 找所有可见的 popup 类元素
                var popups = Array.from(document.querySelectorAll('[class*=popup], [class*=dropdown], [class*=menu], [class*=drawer]'))
                    .filter(function(el) {
                        var r = el.getBoundingClientRect();
                        return r.width>0&&r.height>0&&getComputedStyle(el).display!=='none';
                    })
                    .map(function(el) {
                        return {
                            id: el.id, cls: el.className.toString().slice(0, 80),
                            rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                            text: (el.innerText||'').trim().slice(0, 200)
                        };
                    });
                return {e42_content_info: e42_content ? (function() {
                    var r = e42_content.getBoundingClientRect();
                    return {display: getComputedStyle(e42_content).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (e42_content.innerText||'').trim().slice(0,500), html: e42_content.innerHTML.slice(0, 500)};
                })() : null, all_eduis: all_eduis, popups: popups};
            }""")
            result["after_step2"] = after_step2
            print(f"\n[AFTER STEP2] edui42_content display={after_step2.get('e42_content_info',{}).get('display')} visible={after_step2.get('e42_content_info',{}).get('visible')} rect={after_step2.get('e42_content_info',{}).get('rect')}")
            print(f"[AFTER STEP2] edui42_content text={repr(after_step2.get('e42_content_info',{}).get('text','')[:200])}")
            print(f"[AFTER STEP2] popups count={len(after_step2.get('popups', []))}")
            for p in after_step2.get('popups', [])[:10]:
                print(f"  [{p['id']}] rect={p['rect']} text={repr(p['text'][:80])}")
            for k, v in list(after_step2.get('all_eduis', {}).items())[:5]:
                print(f"  {k}: display={v.get('display')} visible={v.get('visible')} text={repr(v.get('text','')[:60])}")
        else:
            print(f"\n[STEP2] edui42 not visible yet (display={after_step1.get('edui42',{}).get('display')}), checking all eduiN elements")
            # 检查所有 eduiN 的状态
            all_eduis = await page.evaluate("""(function() {
                var result = {};
                for (var i = 1; i <= 60; i++) {
                    var el = document.getElementById('edui' + i);
                    if (el) {
                        var r = el.getBoundingClientRect();
                        result['edui' + i] = {
                            display: getComputedStyle(el).display,
                            visible: r.width>0&&r.height>0,
                            rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                            text: (el.innerText||'').trim().slice(0, 100),
                        };
                    }
                }
                return result;
            })()""")
            result["all_eduis"] = all_eduis
            visible_eduis = {k: v for k, v in all_eduis.items() if v.get('visible') or v.get('display') != 'none'}
            print(f"Visible/block eduis: {list(visible_eduis.keys())}")
            for k, v in list(visible_eduis.items())[:10]:
                print(f"  {k}: display={v.get('display')} visible={v.get('visible')} rect={v.get('rect')} text={repr(v.get('text','')[:60])}")

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

        await page.screenshot(path=str(DEBUG_DIR / "final.png"), full_page=True)

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
"""
debug_insert_v8.py
关键发现（probe2）：
  - hover on edui41_state 后，edui41 显示"插入" text，edui42 变成 display:block
  - edui42 需要在 edui41 hover 之后再 hover 它才会显示完整菜单

现在的方案：
  1. 先 hover edui41_state → 触发 edui41 显示"插入" + edui42 display:block
  2. 等一下让 edui42 显示（CSS transition）
  3. hover edui41_state 的右侧（edui42 区域）→ 显示下拉菜单
  4. 点击"导入文档"选项

问题：之前 Playwright move 已经触发了 edui41 hover，但 edui42 display:block 之后
为什么点击 edui42 没有出现选项？因为"导入文档"选项在 edui42 显示之后还需要进一步交互。
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v8"
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

        # 获取 edui41 和 edui42 的位置
        rects = await page.evaluate("""() => {
            var edui41 = document.getElementById('edui41');
            var edui41_state = document.getElementById('edui41_state');
            var edui42 = document.getElementById('edui42');
            var edui43 = document.getElementById('edui43');
            var result = {};
            if (edui41) {
                var r = edui41.getBoundingClientRect();
                result['edui41'] = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), text: edui41.innerText.trim()};
            }
            if (edui41_state) {
                var r = edui41_state.getBoundingClientRect();
                result['edui41_state'] = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2), text: edui41_state.innerText.trim()};
            }
            if (edui42) {
                var r = edui42.getBoundingClientRect();
                result['edui42'] = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), display: getComputedStyle(edui42).display, visible: r.width>0&&r.height>0, text: (edui42.innerText||'').trim().slice(0,300), html: edui42.innerHTML.slice(0,500)};
            }
            if (edui43) {
                var r = edui43.getBoundingClientRect();
                result['edui43'] = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), display: getComputedStyle(edui43).display, visible: r.width>0&&r.height>0, text: (edui43.innerText||'').trim().slice(0,200)};
            }
            // 找工具栏容器边界
            var toolbar = document.querySelector('.edui-toolbar, [class*=toolbar], #edui41');
            if (toolbar) {
                var r = toolbar.getBoundingClientRect();
                result['toolbar'] = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), text: (toolbar.innerText||'').trim().slice(0,200)};
            }
            return result;
        }""")
        result["rects"] = rects
        print(f"[RECTS] edui41={rects.get('edui41')} edui41_state={rects.get('edui41_state')}")
        print(f"[RECTS] edui42 visible={rects.get('edui42',{}).get('visible')} display={rects.get('edui42',{}).get('display')} html={rects.get('edui42',{}).get('html','')[:200]}")
        print(f"[RECTS] edui43 visible={rects.get('edui43',{}).get('visible')} text={rects.get('edui43',{}).get('text')}")

        # ── 步骤1：hover edui41_state（不在 edui42 上），等待 edui42 显示 ─
        state_rect = rects.get('edui41_state', {})
        edui42_rect = rects.get('edui42', {})
        print(f"\n[STEP1] Hover edui41_state at ({state_rect.get('cx')}, {state_rect.get('cy')})")

        await page.mouse.move(state_rect['cx'], state_rect['cy'])
        result["steps"].append({"step": "hover_edui41", "x": state_rect['cx'], "y": state_rect['cy']})
        print("[STEP1] mouse moved to edui41_state")

        # 等待 CSS transition 让 edui42 显示
        await page.wait_for_timeout(1000)

        # 检查 hover 后 edui42 的状态
        after_hover1 = await page.evaluate("""() => {
            var e42 = document.getElementById('edui42');
            if (!e42) return null;
            var r = e42.getBoundingClientRect();
            return {
                display: getComputedStyle(e42).display,
                visible: r.width>0&&r.height>0,
                rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},
                text: (e42.innerText||'').trim().slice(0,300),
                html: e42.innerHTML.slice(0,800),
                childCount: e42.children.length,
                childTags: Array.from(e42.children).map(function(c){return c.tagName;}),
            };
        }""")
        result["after_hover1"] = after_hover1
        print(f"\n[AFTER HOVER1] edui42 display={after_hover1.get('display')} visible={after_hover1.get('visible')} rect={after_hover1.get('rect')}")
        print(f"[AFTER HOVER1] edui42 text={repr(after_hover1.get('text','')[:200])}")
        print(f"[AFTER HOVER1] edui42 childCount={after_hover1.get('childCount')} childTags={after_hover1.get('childTags')}")
        if after_hover1.get('html'):
            print(f"[AFTER HOVER1] edui42 html={after_hover1['html'][:400]}")

        # ── 步骤2：hover edui42 区域（如果 edui42 已经显示）──
        if after_hover1.get('visible') or after_hover1.get('display') == 'block':
            e42r = after_hover1.get('rect', {})
            # hover edui42 的中心
            e42_cx = e42r.get('x', 0) + e42r.get('w', 0) // 2
            e42_cy = e42r.get('y', 0) + e42r.get('h', 0) // 2
            print(f"\n[STEP2] Hover edui42 at ({e42_cx}, {e42_cy})")
            await page.mouse.move(e42_cx, e42_cy)
            await page.wait_for_timeout(1000)

            # 检查完整菜单是否出现
            after_hover2 = await page.evaluate("""() => {
                // 检查所有可见的 popup/options 元素
                var options = Array.from(document.querySelectorAll('[class*=edui43], [class*=edui44], [class*=edui45], [class*=edui46]'))
                    .filter(function(el) {
                        var r = el.getBoundingClientRect();
                        return r.width>0&&r.height>0&&getComputedStyle(el).display!=='none';
                    })
                    .map(function(el) {
                        return {
                            id: el.id, cls: el.className.toString().slice(0,80),
                            rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                            text: (el.innerText||'').trim().slice(0,200),
                            html: el.innerHTML.slice(0,300)
                        };
                    });

                // 查 edui43
                var e43 = document.getElementById('edui43');
                if (e43) {
                    var r = e43.getBoundingClientRect();
                    var obj = {display: getComputedStyle(e43).display, visible: r.width>0&&r.height>0, rect: {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}, text: (e43.innerText||'').trim().slice(0,300), html: e43.innerHTML.slice(0,500)};
                    options.forEach(function(o) { o.from_edui43 = o.id.startsWith('edui43'); });
                    return obj;
                }
                return {options: options};
            }""")
            result["after_hover2"] = after_hover2
            print(f"\n[AFTER HOVER2] edui43 display={after_hover2.get('display')} visible={after_hover2.get('visible')} text={repr(after_hover2.get('text','')[:200])}")
            if after_hover2.get('options'):
                print(f"[AFTER HOVER2] options count={len(after_hover2.get('options',[]))}")
                for o in after_hover2.get('options', [])[:10]:
                    print(f"  [{o['id']}] rect={o['rect']} text={repr(o['text'][:80])}")
            if after_hover2.get('html'):
                print(f"[AFTER HOVER2] edui43 html={after_hover2['html'][:300]}")

        # ── 方法：既然 hover 已经让 edui42 显示了，直接找"导入文档"选项的 input[type=file] ─
        print("\n[SCANNING] Looking for file input in visible menus")
        file_scan = await page.evaluate("""() => {
            // 先 hover edui41_state（如果在 hover 之前没有 hover）
            var state_el = document.getElementById('edui41_state');
            if (state_el) {
                var r = state_el.getBoundingClientRect();
                var evt = new MouseEvent('mouseover', {bubbles: true, cancelable: true, view: window, clientX: r.x+r.width/2, clientY: r.y+r.height/2, button: 0});
                state_el.dispatchEvent(evt);
            }
            return {
                // 在 body 里找所有 input[type=file]
                file_inputs: Array.from(document.querySelectorAll('input[type=file]')).map(function(el) {
                    return {
                        accept: el.accept,
                        hidden: el.hidden || el.style.display === 'none',
                        visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                        rect: (function() { var r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                        parent_html: (el.parentElement ? el.parentElement.outerHTML.slice(0, 200) : '')
                    };
                }),
                // 找包含"导入文档"文字的元素
                import_doc_els: Array.from(document.querySelectorAll('*'))
                    .filter(function(el) { return (el.innerText||'').trim() === '导入文档' || (el.innerText||'').trim() === '导入'; })
                    .map(function(el) {
                        return {
                            id: el.id, cls: el.className.toString().slice(0,80),
                            rect: (function() { var r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                            text: (el.innerText||'').trim(),
                            html: el.outerHTML.slice(0, 300)
                        };
                    }),
            };
        }""")
        result["file_scan"] = file_scan
        print(f"\n[FILE SCAN] total={len(file_scan.get('file_inputs', []))}")
        for fi in file_scan.get('file_inputs', []):
            print(f"  accept={fi['accept']!r} visible={fi['visible']} rect={fi['rect']} parent={fi['parent_html'][:100]}")
        print(f"\n[IMPORT DOC elements] count={len(file_scan.get('import_doc_els', []))}")
        for ide in file_scan.get('import_doc_els', []):
            print(f"  {ide['id']} rect={ide['rect']} html={ide['html'][:200]}")

        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_v8.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
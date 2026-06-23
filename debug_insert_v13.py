"""
debug_insert_v13.py
关键发现：hover edui41_state 后，edui42_content display=block 但 rect={0,0,0,0} childCount=0
说明 CSS block 激活但没有内容填充（百家号用 JS 动态注入内容）

probe2 里能成功是因为：
1. 移动到 edui41_state 后，等待足够长时间让百家号的 JS 异步加载菜单内容
2. 或者移动鼠标让百家号的 React 状态机处理

新方案：
1. hover edui41_state
2. 然后逐像素向外围移动鼠标（让百家号的 React 认为鼠标仍在工具栏区域内）
3. 找所有包含"导入"的元素（包括 React fiber 注入的临时 DOM）
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_v13"
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

        # 获取 edui41_state 位置
        eval_result = await page.evaluate("""() => {
            var el = document.getElementById('edui41_state');
            if (!el) return {error: 'no edui41_state'};
            var r = el.getBoundingClientRect();
            return {
                cx: Math.round(r.x+r.width/2), cy: Math.round(r.y+r.height/2),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: el.innerText ? el.innerText.trim() : ''
            };
        }""")
        state_rect = eval_result if isinstance(eval_result, dict) and 'error' not in eval_result else {}
        print(f"[STATE] rect={state_rect}")

        # ── 步骤1：hover edui41_state 中心 ──────────────────
        print(f"\n[STEP1] hover to ({state_rect.get('cx')}, {state_rect.get('cy')})")
        await page.mouse.move(state_rect.get('cx', 0), state_rect.get('cy', 0))
        result["steps"].append({"step": "hover_center", "x": state_rect.get('cx'), "y": state_rect.get('cy')})

        # 等待百家号 JS 动态注入菜单内容
        print("[STEP1] waiting 5s for dynamic menu injection...")
        await page.wait_for_timeout(5000)

        snap1 = await page.evaluate("""() => {
            var content = document.getElementById('edui42_content');
            var e42 = document.getElementById('edui42');
            var e43 = document.getElementById('edui43');
            // 扫描所有可见元素
            var all_visible_els = Array.from(document.querySelectorAll('*'))
                .filter(function(el) {
                    var r = el.getBoundingClientRect();
                    var hasSize = r.width > 5 && r.height > 5;
                    var style = getComputedStyle(el);
                    var visible = style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                    return hasSize && visible;
                })
                .map(function(el) {
                    return {
                        id: el.id, cls: el.className.toString().slice(0, 60),
                        rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                        text: (el.innerText||'').trim().slice(0, 80),
                        tag: el.tagName
                    };
                });
            return {
                content_display: content ? getComputedStyle(content).display : null,
                content_rect: content ? (function() { var r=content.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })() : null,
                content_text: content ? (content.innerText||'').trim().slice(0,500) : null,
                content_innerHTML: content ? content.innerHTML.slice(0, 1000) : null,
                content_childCount: content ? content.children.length : null,
                e42_display: e42 ? getComputedStyle(e42).display : null,
                e43_visible: e43 ? (function() { var r=e43.getBoundingClientRect(); return r.width>0&&r.height>0; })() : null,
                e43_text: e43 ? (e43.innerText||'').trim().slice(0,300) : null,
                all_visible_count: all_visible_els.length,
                all_visible_sample: all_visible_els.slice(0, 30),
            };
        }""")
        result["snap1_after_hover_5s"] = snap1
        print(f"\n[AFTER 5s HOVER] content_display={snap1.get('content_display')} content_childCount={snap1.get('content_childCount')} rect={snap1.get('content_rect')}")
        print(f"[AFTER 5s HOVER] content_text={repr(snap1.get('content_text','')[:200])}")
        print(f"[AFTER 5s HOVER] content_innerHTML={snap1.get('content_innerHTML','')[:400]}")
        print(f"[AFTER 5s HOVER] e42_display={snap1.get('e42_display')} e43_visible={snap1.get('e43_visible')} e43_text={repr((snap1.get('e43_text') or '')[:100])}")
        print(f"[AFTER 5s HOVER] all_visible_els count={snap1.get('all_visible_count')}")

        # ── 步骤2：如果内容没有出现，尝试从中心向外扩展移动鼠标 ───
        if not snap1.get('content_text'):
            print("\n[STEP2] trying wider mouse movement pattern")
            cx, cy = state_rect.get('cx', 0), state_rect.get('cy', 0)
            # 移动到 edui41_state 右边缘（edui42 可能在右边展开）
            await page.mouse.move(cx + 40, cy)
            await page.wait_for_timeout(3000)

            snap2 = await page.evaluate("""() => {
                var content = document.getElementById('edui42_content');
                var e42 = document.getElementById('edui42');
                var e43 = document.getElementById('edui43');
                return {
                    content_display: content ? getComputedStyle(content).display : null,
                    content_rect: content ? (function() { var r=content.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })() : null,
                    content_text: content ? (content.innerText||'').trim().slice(0,500) : null,
                    content_innerHTML: content ? content.innerHTML.slice(0, 1000) : null,
                    content_childCount: content ? content.children.length : null,
                    e42_display: e42 ? getComputedStyle(e42).display : null,
                    e43_visible: e43 ? (function() { var r=e43.getBoundingClientRect(); return r.width>0&&r.height>0; })() : null,
                    e43_text: e43 ? (e43.innerText||'').trim().slice(0,300) : null,
                    all_visible_sample: Array.from(document.querySelectorAll('*'))
                        .filter(function(el) { var r=el.getBoundingClientRect(); return r.width>0&&r.height>0&&getComputedStyle(el).display!=='none'; })
                        .map(function(el) { return {id:el.id,cls:el.className.toString().slice(0,60),rect:(function(){var r=el.getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)};})(),text:(el.innerText||'').trim().slice(0,80),tag:el.tagName}; })
                        .slice(0, 30),
                };
            }""")
            result["snap2_after_right_move"] = snap2
            print(f"[AFTER RIGHT MOVE] content_display={snap2.get('content_display')} content_childCount={snap2.get('content_childCount')} rect={snap2.get('content_rect')}")
            print(f"[AFTER RIGHT MOVE] content_text={repr(snap2.get('content_text','')[:200])}")
            print(f"[AFTER RIGHT MOVE] e42_display={snap2.get('e42_display')} e43_visible={snap2.get('e43_visible')} e43_text={repr((snap2.get('e43_text') or '')[:100])}")

        # ── 最终：找 file input 和 import 元素 ─────────────
        final = await page.evaluate("""() => {
            var file_inputs = Array.from(document.querySelectorAll('input[type=file]')).map(function(el) {
                return {accept: el.accept, hidden: el.hidden || el.style.display === 'none', visible: el.offsetWidth>0&&el.offsetHeight>0, rect: (function() { var r=el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })()};
            });
            var import_els = Array.from(document.querySelectorAll('*')).filter(function(el) { return (el.innerText||'').trim().includes('导入文档') || (el.innerText||'').trim().includes('导入'); }).map(function(el) { var r=el.getBoundingClientRect(); return {id:el.id,text:(el.innerText||'').trim().slice(0,100),visible:r.width>0&&r.height>0,rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}}; });
            return {file_inputs: file_inputs, import_els: import_els};
        }""")
        result["final"] = final
        print(f"\n[FINAL] file_inputs={len(final.get('file_inputs', []))} import_els(visible)={len([x for x in final.get('import_els', []) if x.get('visible')])}")
        for fi in [f for f in final.get('file_inputs', []) if f.get('visible')]:
            print(f"  ** FILE INPUT: accept={fi['accept']!r} rect={fi['rect']}")
        for ie in [x for x in final.get('import_els', []) if x.get('visible')]:
            print(f"  ** IMPORT EL: [{ie['id']}] rect={ie['rect']} text={repr(ie['text'])}")

        try:
            await page.screenshot(path=str(DEBUG_DIR / "final.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
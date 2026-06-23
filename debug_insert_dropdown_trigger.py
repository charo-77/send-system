"""
debug_insert_dropdown_trigger.py
目标：稳定触发「插入」下拉菜单，找到「导入文档」选项并拿到其文件上传 input。
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_dropdown_trigger"
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

        # 关闭引导层
        for text in ["我知道了", "下一步", "取消"]:
            try:
                btn = page.get_by_text(text, exact=False).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        # 等待编辑器 ready
        await page.wait_for_selector("#ueditor", timeout=30000)
        await page.wait_for_selector("iframe#ueditor_0", timeout=30000)
        await page.wait_for_timeout(2000)
        result["steps"].append({"step": "editor_ready"})

        # ── 探测初始状态 ───────────────────────────────────
        ui_state = await page.evaluate("""() => {
            return {
                edui41_rect: (() => {
                    const el = document.getElementById('edui41');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                })(),
                edui41_text: (() => {
                    const el = document.getElementById('edui41');
                    return el ? el.innerText.trim() : null;
                })(),
                editor_ui_v2_keys: typeof $EDITORUI_V2 !== 'undefined' ? Object.keys($EDITORUI_V2) : [],
                ue_instant_keys: typeof UE_V2 !== 'undefined' && UE_V2.instants ? Object.keys(UE_V2.instants) : [],
            };
        }""")
        result["ui_state"] = ui_state
        print(f"[INITIAL] edui41_rect={ui_state.get('edui41_rect')} edui41_text={ui_state.get('edui41_text')!r}")
        print(f"[INITIAL] editor_ui_v2_keys count={len(ui_state.get('editor_ui_v2_keys', []))}")
        print(f"[INITIAL] ue_instant_keys={ui_state.get('ue_instant_keys')}")

        # ── 核心步骤：触发「插入」下拉菜单 ───────────────────
        # 方法1: Stateful_onMouseDown + mouseup (百家号 edui 按钮标准触发链)
        r1 = await page.evaluate("""() => {
            const el = document.getElementById('edui41');
            if (!el) return {error: 'edui41 not found'};
            const r = el.getBoundingClientRect();
            const cx = r.x + r.width / 2, cy = r.y + r.height / 2;

            const fire = (type) => el.dispatchEvent(new MouseEvent(type, {
                bubbles: true, cancelable: true, view: window, clientX: cx, clientY: cy, button: 0
            }));

            // 百家号 toolbar 按钮 onmousedown 典型链: mouseover→mousemove→mousedown→mouseup
            fire('mouseover');
            fire('mousemove');
            fire('mousedown');
            fire('mouseup');
            fire('click');

            return {ok: true, cx: Math.round(cx), cy: Math.round(cy), rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
        }""")
        print(f"[METHOD1 mouse sequence] {r1}")
        await page.wait_for_timeout(2000)

        # 方法2: Stateful_onMouseDown 直接调用
        r2 = await page.evaluate("""() => {
            const ins = typeof $EDITORUI_V2 !== 'undefined' && $EDITORUI_V2['edui41'];
            if (!ins) return {error: 'no edui41 instance'};
            const methods = typeof ins === 'object' ? Object.keys(ins).filter(k => typeof ins[k] === 'function') : [];
            let called = null;
            if (typeof ins['Stateful_onMouseDown'] === 'function') {
                try { ins['Stateful_onMouseDown'](); called = 'Stateful_onMouseDown'; } catch(e) { called = 'err: ' + e.message; }
            }
            return {methods: methods.slice(0, 30), called};
        }""")
        print(f"[METHOD2 Stateful_onMouseDown] {r2}")
        await page.wait_for_timeout(1500)

        # 方法3: execCommand insertdoc (通过 editor.execCommand)
        r3 = await page.evaluate("""() => {
            const results = {};
            if (typeof UE_V2 !== 'undefined' && UE_V2.instants) {
                const editor = UE_V2.instants['ueditorInstant0'];
                if (editor) {
                    const methods = Object.keys(editor).filter(k => typeof editor[k] === 'function');
                    results['editor_methods'] = methods.slice(0, 40);
                    // 尝试 execCommand
                    const cmd_map = ['insertdoc', 'importdoc', 'bjhInsertionDrawer', 'openInsertionDrawer'];
                    cmd_map.forEach(cmd => {
                        if (typeof editor.execCommand === 'function') {
                            try { editor.execCommand(cmd); results['exec_' + cmd] = 'called'; } catch(e) { results['exec_' + cmd] = e.message; }
                        }
                    });
                }
            }
            // 搜索所有 $EDITORUI_V2 实例中包含 import/insert/doc/upload 的方法
            if (typeof $EDITORUI_V2 !== 'undefined') {
                const hits = [];
                Object.entries($EDITORUI_V2).forEach(([k, v]) => {
                    if (v && typeof v === 'object') {
                        Object.entries(v).forEach(([mk, mv]) => {
                            if (typeof mv === 'function' && /import|insert|doc|upload/i.test(mk)) {
                                hits.push({instance: k, method: mk});
                            }
                        });
                    }
                });
                results['filtered_methods'] = hits;
            }
            return results;
        }""")
        print(f"[METHOD3 execCommand] {json.dumps(r3, ensure_ascii=False)[:500]}")
        await page.wait_for_timeout(1000)

        # ── 检查下拉菜单状态 ─────────────────────────────────
        popup_state = await page.evaluate("""() => {
            const popups = [];
            const addPopups = (sel, name) => {
                document.querySelectorAll(sel).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 20 || r.height < 20) return;
                    const visible = r.width > 0 && r.height > 0 &&
                        getComputedStyle(el).display !== 'none' &&
                        getComputedStyle(el).visibility !== 'hidden' &&
                        getComputedStyle(el).opacity !== '0';
                    popups.push({
                        name,
                        text: (el.innerText||'').trim().slice(0, 300),
                        cls: el.className.slice(0, 80),
                        id: el.id,
                        visible,
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                    });
                });
            };
            addPopups('[class*="dropdown"]', 'dropdown');
            addPopups('[class*="drawer"]', 'drawer');
            addPopups('[class*="menu"]', 'menu');
            addPopups('[class*="popup"]', 'popup');
            addPopups('[id^="edui_fixedlayer"]', 'edui-fixedlayer');
            addPopups('[class*="insertion"]', 'insertion');
            addPopups('[class*="importdoc"]', 'importdoc');
            addPopups('[class*="import-doc"]', 'import-doc');
            addPopups('[class*="bjh-insertion"]', 'bjh-insertion');
            addPopups('[class*="charu"]', 'charu');

            // 专项检查 edui42 及之后
            const checkEdui = (id) => {
                const el = document.getElementById(id);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {
                    exists: true,
                    visible: r.width > 0 && r.height > 0,
                    rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                    text: (el.innerText||'').trim().slice(0, 500),
                    html: el.outerHTML.slice(0, 800),
                };
            };

            return {
                popups,
                edui42: checkEdui('edui42'),
                edui43: checkEdui('edui43'),
                edui44: checkEdui('edui44'),
                edui45: checkEdui('edui45'),
                edui46: checkEdui('edui46'),
                edui47: checkEdui('edui47'),
                body_snippet: (document.body.innerText||'').slice(0, 3000),
            };
        }""")
        result["popup_state"] = popup_state
        print(f"\n[POPUP] found {len(popup_state['popups'])} popup elements")
        for p in popup_state['popups']:
            print(f"  [{p['name']}] visible={p['visible']} rect={p['rect']} text={repr(p['text'][:120])}")
        for k in ['edui42','edui43','edui44','edui45','edui46','edui47']:
            v = popup_state.get(k)
            if (v):
                print(f"  [{k}] visible={v.get('visible')} rect={v.get('rect')} text={repr(str(v.get('text',''))[:100])}")
                if v.get('html'):
                    print(f"    html={v['html'][:200]}")

        # ── 最终：所有 file input ──────────────────────────
        final = await page.evaluate("""() => {
            const all = Array.from(document.querySelectorAll('input[type="file"]'));
            return {
                count: all.length,
                inputs: all.map(el => ({
                    id: el.id, name: el.name,
                    accept: el.accept,
                    cls: el.className.slice(0, 80),
                    hidden: el.hidden || el.style.display === 'none',
                    visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                    rect: (() => { const r = el.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
                }))
            };
        }""")
        result["file_inputs"] = final
        print(f"\n[FILE INPUTS] total={final['count']}")
        for inp in final['inputs']:
            print(f"  accept={inp['accept']!r} visible={inp['visible']} rect={inp['rect']}")

        # 截图
        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_trigger.png"), full_page=True)
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    # 写结果
    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
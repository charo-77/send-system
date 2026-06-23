"""
debug_insert_cdp.py
用 CDP send 直接执行 JS 函数来触发「插入」下拉菜单
绕过 Playwright 事件模拟的不兼容性
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
DEBUG_DIR = PROJECT_DIR / "debug" / "insert_cdp"
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

        # CDP session
        cdp = await context.new_cdp_session(page)

        # 1. 用 CDP Runtime.evaluate 探查
        probe_result = await cdp.send("Runtime.evaluate", {
            "expression": "(function(){var el=document.getElementById('edui41_state');if(!el)return{error:'no edui41_state'};var ins=$EDITORUI_V2&&$EDITORUI_V2['edui41'];var proto=ins&&ins.__proto__;return{id:el.id,rect:(function(){var r=el.getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}})(),text:el.innerText.trim(),onmousedown:el.getAttribute('onmousedown'),edui41_ins:ins?Object.keys(ins):[],edui41_proto:proto?Object.keys(proto).filter(function(k){return k.includes('Stateful')||k.includes('Mouse')||k.includes('Popup')}):[],edui42_display:(function(){var e=document.getElementById('edui42');return e?getComputedStyle(e).display:null})()};})()"
        })
        info = probe_result.get('result', {}).get('value', {})
        result["probe"] = info
        print(f"[PROBE] edui41_ins={info.get('edui41_ins')} edui41_proto={info.get('edui41_proto')[:10] if isinstance(info.get('edui41_proto'), list) else info.get('edui41_proto')}")
        print(f"[PROBE] onmousedown={info.get('onmousedown')}")
        print(f"[PROBE] edui42_display={info.get('edui42_display')}")

        # 2. CDP Input.dispatchMouseEvent - 发送真实的原始鼠标事件
        rect = info.get('rect', {})
        if rect:
            cx = rect['x'] + rect['w'] // 2
            cy = rect['y'] + rect['h'] // 2
            print(f"\n[CDP MOUSE] dispatching to ({cx}, {cy})")

            await cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": cx,
                "y": cy,
                "button": "none",
                "clickCount": 0
            })
            await asyncio.sleep(0.3)

            await cdp.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": cx,
                "y": cy,
                "button": "left",
                "clickCount": 1
            })
            await asyncio.sleep(0.15)

            await cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": cx,
                "y": cy,
                "button": "left",
                "clickCount": 1
            })

            result["steps"].append({"step": "cdp_mouse", "cx": cx, "cy": cy})
            print("[CDP MOUSE] dispatched mousePressed + mouseReleased")

        await page.wait_for_timeout(2500)

        # 3. 检查 edui42
        check1 = await cdp.send("Runtime.evaluate", {
            "expression": "(function(){var el=document.getElementById('edui42');if(!el)return{error:'no edui42'};var r=el.getBoundingClientRect();return{display:getComputedStyle(el).display,visible:r.width>0&&r.height>0,rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},text:(el.innerText||'').trim().slice(0,300),html:el.innerHTML.slice(0,500)};})()"
        })
        cv = check1.get('result', {}).get('value', {})
        result["check1"] = cv
        print(f"\n[CHECK1] display={cv.get('display')} visible={cv.get('visible')} rect={cv.get('rect')}")

        # 4. 如果没出来，用 CDP 直接调 Stateful 方法
        if not cv.get('visible'):
            print("\n[METHOD2] calling Stateful methods via CDP")
            stateful_r = await cdp.send("Runtime.evaluate", {
                "expression": "(function(){var ins=$EDITORUI_V2&&$EDITORUI_V2['edui41'];var state_el=document.getElementById('edui41_state');if(!ins||!state_el)return{error:'missing'};var proto=ins.__proto__;var r=state_el.getBoundingClientRect();var cx=r.x+r.width/2,cy=r.y+r.height/2;var fireEvent=function(type,button,buttons){var evt=new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,button:button||0,buttons:buttons||0});if(proto['Stateful_onMouseDown']&&type==='mousedown'){proto['Stateful_onMouseDown'].call(ins,evt,state_el);}if(proto['Stateful_onMouseUp']&&type==='mouseup'){proto['Stateful_onMouseUp'].call(ins,evt,state_el);}};fireEvent('mousedown',0,1);fireEvent('mouseup',0,0);return{called:true,proto_methods:proto?Object.keys(proto).filter(function(k){return typeof proto[k]==='function'}):[],stateful_on_proto:proto?Object.keys(proto).filter(function(k){return k.includes('Stateful')}):[]};})()"
            })
            sv = stateful_r.get('result', {}).get('value', {})
            result["stateful_r"] = sv
            print(f"[STATEFUL] called={sv.get('called')} proto_methods={sv.get('proto_methods',[])[:10]} stateful_on_proto={sv.get('stateful_on_proto')}")
            await page.wait_for_timeout(2500)

            check2 = await cdp.send("Runtime.evaluate", {
                "expression": "(function(){var el=document.getElementById('edui42');if(!el)return null;var r=el.getBoundingClientRect();return{display:getComputedStyle(el).display,visible:r.width>0&&r.height>0,rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},text:(el.innerText||'').trim().slice(0,300)};})()"
            })
            cv2 = check2.get('result', {}).get('value', {})
            result["check2"] = cv2
            print(f"[CHECK2] display={cv2.get('display')} visible={cv2.get('visible')}")

        # 5. 方法3: el.click()
        if not cv.get('visible') and not (cv2 and cv2.get('visible')):
            print("\n[METHOD3] state_el.click() via CDP")
            await cdp.send("Runtime.evaluate", {
                "expression": "(function(){var el=document.getElementById('edui41_state');if(el)el.click();})()"
            })
            await page.wait_for_timeout(2500)

            check3 = await cdp.send("Runtime.evaluate", {
                "expression": "(function(){var el=document.getElementById('edui42');if(!el)return null;var r=el.getBoundingClientRect();return{display:getComputedStyle(el).display,visible:r.width>0&&r.height>0,rect:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)},text:(el.innerText||'').trim().slice(0,300)};})()"
            })
            cv3 = check3.get('result', {}).get('value', {})
            result["check3"] = cv3
            print(f"[CHECK3] display={cv3.get('display')} visible={cv3.get('visible')}")

        # ── 最终：所有 file input + visible popups ─────────
        final = await cdp.send("Runtime.evaluate", {
            "expression": "(function(){var popups=Array.from(document.querySelectorAll('[class*=popup],[class*=drawer],[class*=dropdown],[class*=menu]')).filter(function(el){var r=el.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(el).display!=='none';}).map(function(el){return{id:el.id,cls:el.className.toString().slice(0,80),rect:(function(){var r=el.getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}})(),text:(el.innerText||'').trim().slice(0,200)};});var fileInputs=Array.from(document.querySelectorAll('input[type=file]')).map(function(el){return{accept:el.accept,hidden:el.hidden||el.style.display==='none',visible:el.offsetWidth>0&&el.offsetHeight>0,rect:(function(){var r=el.getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)};})()};});return{popups:popups,fileInputs:fileInputs};})()"
        })
        fv = final.get('result', {}).get('value', {})
        result["final"] = fv
        print(f"\n[FINAL] popups={len(fv.get('popups',[]))} fileInputs={len(fv.get('fileInputs',[]))}")
        for p in fv.get('popups', [])[:10]:
            print(f"  [{p['id']}] rect={p['rect']} text={p['text'][:80]}")
        for fi in fv.get('fileInputs', []):
            print(f"  file: accept={fi['accept']} visible={fi['visible']} rect={fi['rect']}")

        # 截图
        try:
            await page.screenshot(path=str(DEBUG_DIR / "after_cdp.png"), full_page=True)
            result["steps"].append({"step": "screenshot"})
        except Exception as e:
            print(f"[SCREENSHOT error] {e}")

        await context.close()

    out_path = DEBUG_DIR / "result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
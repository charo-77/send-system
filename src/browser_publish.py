from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Iterable, List, Callable, Awaitable, Any

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

from articles import Article
from cookies import CookieItem
from html_clipboard import set_html_clipboard


BAIJIAHAO_DOMAINS = [
    ".baidu.com",
    ".baijiahao.baidu.com",
    ".baijiahao.com",
]

DEFAULT_PUBLISH_URLS = [
    "https://baijiahao.baidu.com/builder/rc/edit?type=news",
    "https://baijiahao.baidu.com/builder/rc/article/create",
    "https://baijiahao.baidu.com/builder/rc/home",
]


async def inject_cookies(context, cookies: Iterable[CookieItem], domains: List[str] | None = None) -> int:
    domains = domains or BAIJIAHAO_DOMAINS
    payload = []
    seen = set()
    for c in cookies:
        if not c.name or not c.value:
            continue
        for domain in domains:
            key = (domain, c.name, c.value)
            if key in seen:
                continue
            seen.add(key)
            payload.append({
                "name": c.name,
                "value": c.value,
                "domain": domain,
                "path": c.path or "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            })
    if payload:
        await context.add_cookies(payload)
    return len(payload)


async def first_existing_selector(page: Page, selectors: list[str], timeout_ms: int = 1500) -> str | None:
    deadline = asyncio.get_running_loop().time() + max(timeout_ms, 0) / 1000.0
    while asyncio.get_running_loop().time() < deadline:
        for selector in selectors:
            try:
                if await page.locator(selector).count() > 0:
                    return selector
            except Exception:
                continue
        await page.wait_for_timeout(300)
    return None


async def clear_editor_before_import(page: Page) -> dict:
    result = {"title_cleared": False, "body_cleared": False, "notes": []}
    title_selectors = [
        'textarea[placeholder*="标题"]',
        'input[placeholder*="标题"]',
        '[contenteditable="true"][placeholder*="标题"]',
        '.bjh-editor-title textarea',
        '.title textarea',
    ]
    for sel in title_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count():
                await loc.click(force=True, timeout=2000)
                await page.keyboard.press('Control+A')
                await page.keyboard.press('Backspace')
                result["title_cleared"] = True
                break
        except Exception:
            continue
    try:
        clear_info = await page.evaluate(
            """() => {
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 20 && r.height > 20 && s.display !== 'none' && s.visibility !== 'hidden';
                };
                const targets = Array.from(document.querySelectorAll('[contenteditable="true"], .ProseMirror, .ql-editor, .public-DraftEditor-content [contenteditable="true"]')).filter(visible);
                let count = 0;
                for (const el of targets) {
                    const text = (el.innerText || el.textContent || '').trim();
                    if (!text && !el.querySelector('img')) continue;
                    el.focus();
                    el.innerHTML = '';
                    el.textContent = '';
                    for (const type of ['beforeinput','input','change','blur']) {
                        try { el.dispatchEvent(new Event(type, {bubbles:true})); } catch (_) {}
                    }
                    count += 1;
                }
                return {count, targets: targets.length};
            }"""
        )
        result["body_cleared"] = bool((clear_info or {}).get("count") or (clear_info or {}).get("targets"))
        result["clear_info"] = clear_info
    except Exception as e:
        result["notes"].append(f"clear_body_exception: {type(e).__name__}: {e}")
    await page.wait_for_timeout(800)
    return result


async def fill_article_form(page: Page, article: Article) -> dict:
    result = {"title_filled": False, "body_filled": False, "notes": [], "steps": []}
    title_text = (article.title or '').strip()
    body_text = (article.body or '').strip()
    # Do not pre-truncate title. Let the platform/browser validate and report any title problem.
    if title_text and body_text and body_text.startswith(title_text):
        deduped_body = body_text[len(title_text):].lstrip('\r\n ').strip()
        if deduped_body:
            body_text = deduped_body
            result["notes"].append("removed duplicated title from body head")

    try:
        ready_selector = await first_existing_selector(
            page,
            [
                '#ueditor',
                'iframe#ueditor_0',
                'iframe[id*="ueditor" i]',
                '[data-testid="news-title-input"] [contenteditable="true"]',
                '[data-testid="news-title-input"] input',
                '[data-testid="news-title-input"] textarea',
                'textarea[placeholder*="标题"]',
                'input[placeholder*="标题"]',
                'text=请输入标题',
                'text=请输入正文',
            ],
            timeout_ms=30000,
        )
        if not ready_selector:
            raise PlaywrightTimeoutError('editor shell selectors not found within 30s')
        result["editor_ready_selector"] = ready_selector
        result["steps"].append({"step": "ready_selector", "ok": True, "selector": ready_selector})
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping.txt').write_text('entered fill_article_form', encoding='utf-8')
        try:
            result["editor_probe_before_fill"] = await probe_editor_surface(page)
        except Exception as probe_error:
            result["steps"].append({"step": "editor_probe_before_fill", "ok": False, "error": str(probe_error)[:500]})
            result["notes"].append(f"editor_probe_before_fill failed: {probe_error}")
        await page.wait_for_timeout(100)
    except PlaywrightTimeoutError as e:
        result["steps"].append({"step": "ready_selector", "ok": False, "error": str(e)})
        result["notes"].append(f"editor shell not ready: {e}")

    try:
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_title.txt').write_text('before title path', encoding='utf-8')
        title_sel = await first_existing_selector(
            page,
            [
                '[data-testid="news-title-input"] [contenteditable="true"][data-lexical-editor="true"]',
                '[data-testid="news-title-input"] [contenteditable="true"]',
                '[data-testid="news-title-input"] textarea',
                '[data-testid="news-title-input"] input',
                'textarea[placeholder*="标题"]',
                'input[placeholder*="标题"]',
                '[contenteditable="true"][aria-label*="标题"]',
            ],
            timeout_ms=12000,
        )
        if not title_sel:
            raise RuntimeError('title selector not found')
        result["steps"].append({"step": "title_selector", "ok": True, "selector": title_sel})
        title_loc = page.locator(title_sel).first
        await title_loc.wait_for(timeout=15000)
        tag_name = await title_loc.evaluate("el => el.tagName")
        result["steps"].append({"step": "title_tag", "ok": True, "tag": tag_name})
        if tag_name in ('INPUT', 'TEXTAREA'):
            await title_loc.fill(title_text)
            actual_title_text = await title_loc.input_value(timeout=3000)
            result["steps"].append({"step": "title_fill_input", "ok": True, "value_len": len(actual_title_text or '')})
            if title_text and title_text not in (actual_title_text or ''):
                raise RuntimeError(f"title verification failed, got={actual_title_text!r}")
            result["title_filled"] = True
        else:
            await title_loc.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.insert_text(title_text)
            await page.wait_for_timeout(800)
            actual_title_text = await title_loc.evaluate("el => (el.innerText || el.textContent || el.getAttribute('value') || '').trim()")
            result["steps"].append({"step": "title_fill_contenteditable_keyboard", "ok": True, "value_len": len(actual_title_text or '')})
            if title_text and title_text not in (actual_title_text or ''):
                await title_loc.evaluate("(el, value) => { el.innerText = value; el.textContent = value; el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:value})); el.dispatchEvent(new Event('change', {bubbles:true})); }", title_text)
                await page.wait_for_timeout(500)
                actual_title_text = await title_loc.evaluate("el => (el.innerText || el.textContent || el.getAttribute('value') || '').trim()")
                result["steps"].append({"step": "title_fill_contenteditable_direct_set", "ok": True, "value_len": len(actual_title_text or '')})
            if title_text and title_text not in (actual_title_text or ''):
                raise RuntimeError(f"contenteditable title verification failed, got={actual_title_text!r}")
            result["title_filled"] = True
        result["title_target"] = title_sel
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_title_done.txt').write_text('title done', encoding='utf-8')
    except Exception as e:
        result["steps"].append({"step": "title_fill", "ok": False, "error": str(e)[:500]})
        result["notes"].append(f"title fill failed: {e}")

    typing_text = body_text
    if len(typing_text) > 12000:
        result["notes"].append(f"body truncated from {len(typing_text)} to 12000 chars for stable typing")
        typing_text = typing_text[:12000]

    try:
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_iframe.txt').write_text('before iframe path', encoding='utf-8')
        frame_el = await page.wait_for_selector("iframe#ueditor_0, iframe[id*=\"ueditor\" i]", timeout=8000)
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_iframe_selector_done.txt').write_text('iframe selector done', encoding='utf-8')
        result["steps"].append({"step": "iframe_selector", "ok": True})
        frame = await frame_el.content_frame()
        if frame is None:
            raise RuntimeError("ueditor iframe content_frame is None")
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_iframe_frame_done.txt').write_text('iframe frame done', encoding='utf-8')
        result["steps"].append({"step": "iframe_content_frame", "ok": True})
        await frame.wait_for_load_state("domcontentloaded", timeout=30000)
        result["steps"].append({"step": "iframe_domcontentloaded", "ok": True})
        body = frame.locator("body").first
        await body.wait_for(timeout=15000)
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_iframe_body_ready.txt').write_text('iframe body ready', encoding='utf-8')
        result["steps"].append({"step": "iframe_body_ready", "ok": True})
        await body.click(force=True, timeout=5000)
        result["steps"].append({"step": "iframe_body_click", "ok": True, "skipped": False, "reason": "iframe evaluate + focus sync path"})
        try:
            await body.evaluate("el => { el.focus(); }")
        except Exception:
            pass
        escaped_lines = [line.strip() for line in typing_text.splitlines() if line.strip()]
        paste_info = await body.evaluate(
            """(el, lines) => {
                const safe = (s) => String(s || '').replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
                const arr = Array.isArray(lines) ? lines.filter(Boolean) : [];
                el.innerHTML = arr.length ? arr.map(line => `<p>${safe(line)}</p>`).join('') : '<p><br></p>';
                el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: arr.join('\n') }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                if (window.parent && window.parent.UE && window.parent.UE.instants) {
                    try {
                        const keys = Object.keys(window.parent.UE.instants || {});
                        if (keys.length) {
                            const ed = window.parent.UE.instants[keys[0]];
                            if (ed && typeof ed.fireEvent === 'function') {
                                ed.fireEvent('contentchange');
                            }
                            if (ed && typeof ed.execCommand === 'function') {
                                try { ed.execCommand('insertparagraph'); } catch (_) {}
                            }
                        }
                    } catch (_) {}
                }
                return {
                    method: 'iframe_body_innerhtml_set',
                    textPrefix: (el.innerText || '').slice(0, 200),
                    htmlPrefix: (el.innerHTML || '').slice(0, 500),
                    textLength: (el.innerText || '').length,
                    imgCount: el.querySelectorAll('img').length,
                };
            }""",
            escaped_lines,
        )
        Path(r'D:\milu_publish_reverse_20260513\debug\worker_pool_live\_fill_ping_iframe_type_done.txt').write_text('iframe type done', encoding='utf-8')
        result["steps"].append({"step": "iframe_body_type", "ok": True, "typed_len": len(typing_text), "chunks": len(chunks)})
        await page.wait_for_timeout(1200)
        page_count = ''
        try:
            page_count = await page.locator('#editWorldCount .count').inner_text(timeout=3000)
        except Exception:
            page_count = ''
        placeholder_still_visible = False
        try:
            placeholder_still_visible = await page.locator('text=请输入正文').first.is_visible(timeout=1500)
        except Exception:
            placeholder_still_visible = False
        count_digits = ''.join(ch for ch in str(page_count) if ch.isdigit())
        count_value = int(count_digits) if count_digits else 0
        text_len = int(paste_info.get("textLength") or 0)
        result["body_filled"] = bool(count_value >= 200 and text_len >= 200 and not placeholder_still_visible)
        result["body_target"] = {**paste_info, "pageWordCount": page_count, "pageWordCountValue": count_value, "placeholderStillVisible": placeholder_still_visible, "strategy": "iframe_ueditor"}
        result["steps"].append({"step": "iframe_body_verify", "ok": bool(result["body_filled"]), "text_len": text_len, "page_count": page_count, "page_count_value": count_value, "placeholder_still_visible": placeholder_still_visible})
        if not result["body_filled"]:
            result["notes"].append("iframe body write finished but page word count/placeholder check says body is still not accepted")
    except Exception as iframe_error:
        result["steps"].append({"step": "iframe_body_path", "ok": False, "error": str(iframe_error)[:500]})
        result["notes"].append(f"iframe body path failed: {iframe_error}")
        try:
            body_sel = await first_existing_selector(
                page,
                [
                    '[contenteditable="true"][data-placeholder*="正文"]',
                    '[contenteditable="true"][aria-label*="正文"]',
                    '.ProseMirror',
                    '.ql-editor',
                    '.public-DraftEditor-content [contenteditable="true"]',
                    '[data-testid*="editor"] [contenteditable="true"]',
                    '[data-testid*="content"] [contenteditable="true"]',
                ],
                timeout_ms=12000,
            )
            if not body_sel:
                raise RuntimeError('fallback body selector not found')
            result["steps"].append({"step": "fallback_body_selector", "ok": True, "selector": body_sel})
            body_loc = page.locator(body_sel).first
            await body_loc.wait_for(timeout=15000)
            await body_loc.click(force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.insert_text(typing_text)
            result["steps"].append({"step": "fallback_body_type", "ok": True, "typed_len": len(typing_text)})
            await page.wait_for_timeout(1200)
            body_info = await body_loc.evaluate(
                """(el, payload) => {
                    const lines = Array.isArray(payload?.lines) ? payload.lines : [];
                    const html = lines.map(x => `<p>${String(x).replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c] || c))}</p>`).join('');
                    const setNativeValue = target => {
                        try {
                            target.focus();
                            if ('innerHTML' in target) target.innerHTML = html;
                            if ('textContent' in target) target.textContent = lines.join('\n');
                            for (const type of ['beforeinput','input','change','blur']) {
                                try { target.dispatchEvent(new Event(type, { bubbles: true })); } catch (_) {}
                            }
                        } catch (_) {}
                    };
                    setNativeValue(el);
                    return {
                        method: 'contenteditable.insert_text+dom_patch',
                        textPrefix: (el.innerText || el.textContent || '').slice(0, 200),
                        htmlPrefix: (el.innerHTML || '').slice(0, 500),
                        textLength: (el.innerText || el.textContent || '').length,
                        imgCount: el.querySelectorAll ? el.querySelectorAll('img').length : 0,
                    };
                }""",
                {"lines": body_lines}
            )
            verify = await verify_imported_content(page, article=None)
            result["body_filled"] = bool(body_info.get("textLength") or body_info.get("imgCount") or verify.get("word_count_ok"))
            result["body_target"] = {**body_info, "strategy": "main_document_contenteditable", "selector": body_sel, "verify": verify}
            if not result["body_filled"]:
                patch_verify = await page.evaluate(
                    """(payload) => {
                        const lines = Array.isArray(payload?.lines) ? payload.lines : [];
                        const html = lines.map(x => `<p>${String(x).replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c] || c))}</p>`).join('');
                        const targets = Array.from(document.querySelectorAll('[contenteditable="true"], .ProseMirror, .ql-editor, .public-DraftEditor-content [contenteditable="true"]'));
                        const visible = el => {
                            if (!el) return false;
                            const r = el.getBoundingClientRect();
                            const s = window.getComputedStyle(el);
                            return r.width > 8 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
                        };
                        let best = targets.find(visible) || targets[0] || null;
                        if (!best) return { ok:false, reason:'no-editor-target' };
                        best.focus();
                        best.innerHTML = html;
                        best.textContent = lines.join('\n');
                        for (const type of ['beforeinput','input','change','blur']) {
                            try { best.dispatchEvent(new Event(type, { bubbles: true })); } catch (_) {}
                        }
                        return { ok:true, textLength:(best.innerText || best.textContent || '').length, htmlPrefix:(best.innerHTML || '').slice(0,500) };
                    }""",
                    {"lines": body_lines}
                )
                await page.wait_for_timeout(1500)
                verify = await verify_imported_content(page, article=None)
                result["body_filled"] = bool((patch_verify or {}).get("textLength") or verify.get("word_count_ok"))
                result["body_target"] = {**result.get("body_target", {}), "patch_verify": patch_verify, "verify_after_patch": verify}
                if not result["body_filled"]:
                    result["notes"].append("contenteditable fallback typed but body still looks empty")
        except Exception as fallback_error:
            result["steps"].append({"step": "fallback_body_path", "ok": False, "error": str(fallback_error)[:500]})
            result["notes"].append(f"body typing failed: {fallback_error}")

    result["editor_probe_after_fill"] = {"skipped": True}
    return result


async def probe_editor_surface(page: Page) -> dict:
    try:
        return await page.evaluate(r"""() => {
            const textOf = el => (el?.innerText || el?.textContent || el?.value || '').replace(/\s+/g, ' ').trim();
            const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 8 && r.height > 8 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const pickVisible = selectors => {
                for (const selector of selectors) {
                    const hit = Array.from(document.querySelectorAll(selector)).find(visible);
                    if (hit) return hit;
                }
                return null;
            };
            const pickTitle = () => {
                const selectors = [
                    '[data-testid="news-title-input"] textarea',
                    '[data-testid="news-title-input"] input',
                    '[data-testid="news-title-input"] [contenteditable="true"][data-lexical-editor="true"]',
                    '[data-testid="news-title-input"] [contenteditable="true"]',
                    'textarea[placeholder*="标题"]',
                    'input[placeholder*="标题"]',
                    '[contenteditable="true"][aria-label*="标题"]',
                ];
                for (const selector of selectors) {
                    const nodes = Array.from(document.querySelectorAll(selector)).filter(visible);
                    const good = nodes.find(el => {
                        const r = el.getBoundingClientRect();
                        const text = textOf(el);
                        const placeholder = el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || el.getAttribute('aria-label') || '';
                        return r.width > 120 && r.height >= 20 && r.height < 120 && (
                            /标题/.test(placeholder) ||
                            el.tagName === 'INPUT' ||
                            el.tagName === 'TEXTAREA' ||
                            el.getAttribute('data-lexical-editor') === 'true' ||
                            text.length <= 120
                        );
                    });
                    if (good) return good;
                }
                return null;
            };
            const bodyText = document.body?.innerText || '';
            const titleEl = pickTitle();
            const contenteditables = Array.from(document.querySelectorAll('[contenteditable="true"]')).slice(0, 24).map((el, i) => ({
                i,
                tag: el.tagName,
                text: textOf(el).slice(0, 120),
                cls: String(el.className || ''),
                id: el.id || '',
                role: el.getAttribute('role') || '',
                placeholder: el.getAttribute('placeholder') || el.getAttribute('data-placeholder') || el.getAttribute('aria-label') || '',
                visible: visible(el),
                rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })(),
            }));
            const iframes = Array.from(document.querySelectorAll('iframe')).slice(0, 20).map((el, i) => ({
                i,
                id: el.id || '',
                name: el.getAttribute('name') || '',
                title: el.getAttribute('title') || '',
                src: el.getAttribute('src') || '',
                cls: String(el.className || ''),
                visible: visible(el),
                rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })(),
            }));
            const inputs = Array.from(document.querySelectorAll('input,textarea')).slice(0, 40).map((el, i) => ({
                i,
                tag: el.tagName,
                type: el.getAttribute('type') || '',
                value: textOf(el).slice(0, 120),
                cls: String(el.className || ''),
                id: el.id || '',
                name: el.getAttribute('name') || '',
                placeholder: el.getAttribute('placeholder') || el.getAttribute('aria-label') || '',
                visible: visible(el),
                rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })(),
            }));
            const labeledNodes = Array.from(document.querySelectorAll('button,[role="button"],a,div,span,label,h1,h2,h3,p')).filter(visible).map((el, i) => ({
                i,
                tag: el.tagName,
                text: textOf(el).slice(0, 80),
                cls: String(el.className || ''),
                id: el.id || '',
            })).filter(x => x.text && /标题|正文|图文|文章|发布|创作|输入|写/.test(x.text)).slice(0, 80);
            const buttonTexts = Array.from(document.querySelectorAll('button,[role="button"],a,div,span')).filter(visible).map(textOf).filter(Boolean).slice(0, 120);
            const countCandidates = Array.from(document.querySelectorAll('#editWorldCount .count, #editWorldCount, [class*="word"] [class*="count"], [class*="count"], span, div'))
                .filter(visible)
                .map(el => {
                    const t = textOf(el);
                    const r = el.getBoundingClientRect();
                    return { text: t, w: r.width, h: r.height };
                })
                .filter(x => x.text && x.text.length <= 24 && x.w < 220 && x.h < 80)
                .map(x => x.text)
                .filter(t => /^\d+\/\d+$/.test(t) || /^\d+$/.test(t) || /^\d+\s*字$/.test(t));
            const hasUeditorFrame = iframes.some(x => x.visible && (x.id === 'ueditor_0' || /ueditor/i.test(x.id) || /ueditor/i.test(x.name)));
            const hasEditorContentEditable = contenteditables.some(x => x.visible && (
                /正文/.test(x.placeholder || '') ||
                /editor|content|rich|article|body/i.test(`${x.id} ${x.cls} ${x.role}`) ||
                (x.rect.w > 360 && x.rect.h > 140)
            ));
            const hasEditorShell = !!document.querySelector('[class*="FeEditor"], [class*="editor"], [class*="Editor"], [data-testid*="editor"], [data-testid*="content"]');
            const hasPublishButton = buttonTexts.some(t => t === '发布' || t === '继续发布' || t === '提交发布' || t === '预览并发布');
            const hasCoverEntry = buttonTexts.some(t => /封面/.test(t));
            const hasActivityEntry = buttonTexts.some(t => /活动|投稿/.test(t));
            const hasTitlePlaceholder = /请输入标题|标题/.test(bodyText) || contenteditables.some(x => /标题/.test(x.placeholder || ''));
            const hasBodyPlaceholder = /请输入正文|添加正文|正文/.test(bodyText) || contenteditables.some(x => /正文/.test(x.placeholder || ''));
            const shellReady = /builder\/rc\/(edit|article\/create)/.test(location.href) || hasPublishButton || hasEditorShell;
            const editorReady = !!titleEl && (hasUeditorFrame || hasEditorContentEditable || hasBodyPlaceholder || hasCoverEntry || hasActivityEntry);
            return {
                url: location.href,
                titleText: titleEl ? textOf(titleEl) : '',
                countText: countCandidates[0] || '',
                bodyTextSnippet: bodyText.slice(0, 1500),
                titleFound: !!titleEl,
                hasTitlePlaceholder,
                hasBodyPlaceholder,
                shellReady,
                editorReady,
                state: editorReady ? 'editor_ready' : (shellReady ? 'shell_ready' : 'not_ready'),
                bodyReadySignals: {
                    hasUeditorFrame,
                    hasEditorContentEditable,
                    hasEditorShell,
                    hasPublishButton,
                    hasCoverEntry,
                    hasActivityEntry,
                },
                contenteditables,
                iframes,
                inputs,
                labeledNodes,
                button_texts: buttonTexts,
            };
        }""")
    except Exception as e:
        return {"state": "probe_failed", "error": str(e)[:500], "url": page.url}


async def inspect_editor_initial_state(page: Page, article: Article | None = None) -> dict:
    result = {
        "url": "",
        "title_value": "",
        "word_count_text": "",
        "word_count_value": None,
        "has_body_placeholder": False,
        "has_title_placeholder": False,
        "has_captcha": False,
        "has_latest_draft": False,
        "is_dirty_existing_draft": False,
        "body_snippet": "",
        "notes": [],
    }
    try:
        snap = await probe_editor_surface(page)
        body_text = snap.get("bodyTextSnippet") or ""
        result["url"] = snap.get("url") or ""
        result["title_value"] = snap.get("titleText") or ""
        result["word_count_text"] = snap.get("countText") or ""
        digits = ''.join(ch for ch in result["word_count_text"] if ch.isdigit())
        result["word_count_value"] = int(digits) if digits else 0
        result["has_body_placeholder"] = bool(snap.get("hasBodyPlaceholder"))
        result["has_title_placeholder"] = bool(snap.get("hasTitlePlaceholder"))
        low = body_text.lower()
        page_url = (result.get("url") or "").lower()
        result["has_captcha"] = (
            ('百度安全验证' in body_text) or ('安全验证' in body_text) or ('验证码' in body_text)
            or ('captcha' in low)
            or ('verify' in low and 'security' in low)
            or ('vcode' in low)
            or ('wappass.baidu.com' in page_url)
            or ('verify' in page_url and 'baidu' in page_url)
            or ('captcha' in page_url)
        )
        result["has_latest_draft"] = any(token in body_text for token in ['最近保存', '最新草稿', '继续编辑', '草稿'])
        result["body_snippet"] = body_text[:1200]
        result["editor_probe"] = snap
        result["is_dirty_existing_draft"] = bool(
            result["title_value"]
            and not result["has_title_placeholder"]
            and not result["has_latest_draft"]
            and (result["word_count_value"] or 0) > 0
        )
        if result["has_captcha"]:
            result["notes"].append("captcha visible on initial page")
        if result["is_dirty_existing_draft"]:
            result["notes"].append("page looks like existing draft instead of clean new page")
    except Exception as e:
        result["notes"].append(f"inspect initial state failed: {e}")
    return result


async def verify_imported_content(page: Page, article: Article | None = None) -> dict:
    result = {
        "ok": False,
        "title_ok": False,
        "body_ok": False,
        "word_count_ok": False,
        "placeholder_present": None,
        "title_value": "",
        "word_count_text": "",
        "word_count_value": None,
        "body_length": 0,
        "body_preview": "",
        "notes": [],
    }

    try:
        await page.wait_for_timeout(2500)
        state = await probe_editor_surface(page)
        result["title_value"] = state.get("titleText") or ""
        result["word_count_text"] = state.get("countText") or ""
        result["placeholder_present"] = state.get("hasBodyPlaceholder")
        result["editor_probe"] = state
        try:
            digits = ''.join(ch for ch in result["word_count_text"] if ch.isdigit())
            result["word_count_value"] = int(digits) if digits else 0
        except Exception:
            result["word_count_value"] = 0
        result["word_count_ok"] = bool((result["word_count_value"] or 0) > 0)
    except Exception as e:
        result["notes"].append(f"page state probe failed: {e}")

    try:
        frame_el = await page.wait_for_selector('iframe#ueditor_0, iframe[id*="ueditor" i]', timeout=15000)
        frame = await frame_el.content_frame()
        if frame is None:
            raise RuntimeError('iframe#ueditor_0 content_frame is None')
        body_info = await frame.locator('body').first.evaluate(r"""el => ({
            text: (el.innerText || '').trim(),
            html: (el.innerHTML || '').trim(),
            imgCount: el.querySelectorAll('img').length,
        })""")
        body_text = (body_info.get('text') or '').strip()
        body_html = body_info.get('html') or ''
        img_count = int(body_info.get('imgCount') or 0)
        result["body_length"] = len(body_text)
        result["body_preview"] = body_text[:300]
        result["body_ok"] = bool(body_text or img_count or ('<img' in body_html.lower()))
        result["body_strategy"] = 'iframe_ueditor'
    except Exception as e:
        result["notes"].append(f"iframe body probe failed: {e}")
        try:
            fallback = await page.evaluate(r"""() => {
                const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return r.width > 8 && r.height > 8 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const selectors = [
                    '[contenteditable="true"][data-placeholder*="正文"]',
                    '[contenteditable="true"][aria-label*="正文"]',
                    '.ProseMirror',
                    '.ql-editor',
                    '.public-DraftEditor-content [contenteditable="true"]',
                    '[data-testid*="editor"] [contenteditable="true"]',
                    '[data-testid*="content"] [contenteditable="true"]',
                ];
                for (const selector of selectors) {
                    const hit = Array.from(document.querySelectorAll(selector)).find(visible);
                    if (hit) {
                        return {
                            selector,
                            text: textOf(hit),
                            html: (hit.innerHTML || '').trim(),
                            imgCount: hit.querySelectorAll ? hit.querySelectorAll('img').length : 0,
                        };
                    }
                }
                return null;
            }""")
            if fallback:
                const_text = (fallback.get('text') or '').strip()
                const_html = fallback.get('html') or ''
                const_imgs = int(fallback.get('imgCount') or 0)
                result["body_length"] = len(const_text)
                result["body_preview"] = const_text[:300]
                result["body_ok"] = bool(const_text or const_imgs or ('<img' in const_html.lower()))
                result["body_strategy"] = fallback.get('selector') or 'main_document_contenteditable'
            else:
                result["notes"].append('fallback body probe found no visible contenteditable editor')
        except Exception as fallback_error:
            result["notes"].append(f"fallback body probe failed: {fallback_error}")

    if article is not None:
        expected = (article.title or '').strip()
        actual = (result.get('title_value') or '').strip()
        result["title_ok"] = bool(expected and actual and expected == actual)
        if not result["title_ok"]:
            result["notes"].append(f"title mismatch: expected={expected!r}, actual={actual!r}")
    else:
        result["title_ok"] = bool(result.get('title_value'))

    if result.get("placeholder_present") and not result.get("body_ok"):
        result["notes"].append("editor still shows body placeholder")

    result["ok"] = bool(result["title_ok"] and result["body_ok"] and result["word_count_ok"])
    if not result["word_count_ok"]:
        result["notes"].append(f"word count not ready: {result.get('word_count_text')!r}")
    if not result["body_ok"]:
        result["notes"].append("editor body is still empty")
    return result


async def click_footer_publish_by_dom(page: Page) -> dict | None:
    """Click the editor footer's real publish button under any overlay/modal/tour.

    This deliberately does NOT inspect, close, or depend on popups. It selects the
    bottom editor action button by text + button/class + footer-like viewport
    position, then dispatches DOM events directly on that underlying element.
    """
    return await page.evaluate(
        r"""() => {
            const isPublish = el => {
                const t = (el.innerText || el.value || el.textContent || '').trim();
                return t === '发布' || t === '继续发布';
            };
            const candidates = Array.from(document.querySelectorAll('button.cheetah-btn, button, .op-btn-outter-content'))
                .filter(isPublish)
                .map(el => {
                    const r = el.getBoundingClientRect();
                    const cls = String(el.className || '');
                    const score =
                        (el.tagName === 'BUTTON' ? 100 : 0) +
                        (cls.includes('cheetah-btn-primary') ? 80 : 0) +
                        (cls.includes('cheetah-btn-solid') ? 30 : 0) +
                        // The real publish action is in the sticky bottom toolbar.
                        (r.y > window.innerHeight * 0.55 ? 60 : 0) +
                        (r.width >= 70 && r.height >= 30 ? 20 : 0) -
                        // Avoid modal/header/sidebar buttons if one ever has the same text.
                        (r.y < window.innerHeight * 0.35 ? 80 : 0);
                    return {el, r, cls, score};
                })
                .filter(x => x.r.width > 20 && x.r.height > 20 && x.r.x >= 0 && x.r.y >= 0)
                .sort((a, b) => b.score - a.score || b.r.y - a.r.y);
            const picked = candidates[0];
            if (!picked) return null;
            const el = picked.el;
            const r = picked.r;
            const detail = {
                text: (el.innerText || el.value || el.textContent || '').trim(),
                tag: el.tagName,
                cls: picked.cls,
                id: el.id || '',
                score: picked.score,
                rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                center: {x: r.x + r.width / 2, y: r.y + r.height / 2},
                candidateCount: candidates.length,
            };
            try { el.focus({preventScroll: true}); } catch (_) {}
            if (typeof el.click === 'function') {
                el.click();
            }
            // React/Cheetah usually listens on bubbling pointer/mouse/click events.
            for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                el.dispatchEvent(new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: detail.center.x,
                    clientY: detail.center.y,
                    button: 0,
                }));
            }
            return detail;
        }"""
    )


async def click_visible_text_by_dom(page: Page, text: str, selectors: str, prefer_last: bool = True) -> dict | None:
    """Click a text-matched element by DOM events. Use only for deliberate second-step dialogs."""
    return await page.evaluate(
        """({text, selectors, preferLast}) => {
            const els = Array.from(document.querySelectorAll(selectors));
            const visible = els.filter(el => {
                const t = (el.innerText || el.value || el.textContent || '').trim();
                const r = el.getBoundingClientRect();
                return t === text && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
            });
            const el = preferLast ? visible[visible.length - 1] : visible[0];
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const detail = {
                text: (el.innerText || el.value || el.textContent || '').trim(),
                tag: el.tagName,
                cls: String(el.className || ''),
                id: el.id || '',
                rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                center: {x: r.x + r.width / 2, y: r.y + r.height / 2},
            };
            try { el.focus({preventScroll: true}); } catch (_) {}
            if (typeof el.click === 'function') {
                el.click();
            }
            for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                el.dispatchEvent(new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: detail.center.x,
                    clientY: detail.center.y,
                    button: 0,
                }));
            }
            return detail;
        }""",
        {"text": text, "selectors": selectors, "preferLast": prefer_last},
    )


async def click_graphic_tab(page: Page) -> dict | None:
    return await page.evaluate(
        r"""() => {
            const textOf = el => (el?.innerText || el?.textContent || el?.value || '').replace(/\s+/g, ' ').trim();
            const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 20 && r.height > 20 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const score = el => {
                const txt = textOf(el);
                const cls = String(el.className || '');
                let s = 0;
                if (txt === '图文') s += 100;
                if (/list-item/.test(cls)) s += 40;
                if (/item-active/.test(cls)) s += 20;
                if (/header-list-content|edit-header|center-area-content/.test(cls)) s += 10;
                return s;
            };
            const candidates = Array.from(document.querySelectorAll('div,span,button,a,label')).filter(el => visible(el) && textOf(el) === '图文');
            candidates.sort((a, b) => score(b) - score(a));
            const el = candidates[0];
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const detail = {
                text: textOf(el),
                tag: el.tagName,
                cls: String(el.className || ''),
                id: el.id || '',
                rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                center: {x: r.x + r.width / 2, y: r.y + r.height / 2},
                candidateCount: candidates.length,
            };
            try { el.focus({preventScroll: true}); } catch (_) {}
            if (typeof el.click === 'function') el.click();
            for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                el.dispatchEvent(new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: detail.center.x,
                    clientY: detail.center.y,
                    button: 0,
                }));
            }
            return detail;
        }"""
    )


async def try_enter_news_editor_from_home(page: Page) -> dict:
    result = {"attempted": True, "clicked": [], "final_url": page.url, "ok": False}

    async def _probe_publish_menu() -> dict:
        return await page.evaluate(
            r'''() => {
                const textOf = el => ((el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim());
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 10 && r.height > 10 && r.x >= 0 && r.y >= 0;
                };
                const nodes = Array.from(document.querySelectorAll('button,[role=button],a,div,span,label')).filter(visible).map((el, i) => {
                    const t = textOf(el);
                    const cls = String(el.className || '');
                    const id = el.id || '';
                    const r = el.getBoundingClientRect();
                    return {i, text:t, cls, id, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                });
                const publishBtn = document.getElementById('home-publish-btn');
                return {
                    hasPublishBtn: !!publishBtn,
                    publishBtn: publishBtn ? {text:textOf(publishBtn), cls:String(publishBtn.className||''), id:publishBtn.id} : null,
                    graphCandidates: nodes.filter(x => /发布图文|图文|写文章|文章/.test(x.text)).slice(0, 20),
                    publishCandidates: nodes.filter(x => /发布作品|去发布|立即发布|开始创作/.test(x.text) || x.id === 'home-publish-btn').slice(0, 20),
                };
            }'''
        )

    async def _click_publish_btn_and_graphic() -> bool:
        first = await page.evaluate(
            r'''() => {
                const textOf = el => ((el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim());
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 10 && r.height > 10 && r.x >= 0 && r.y >= 0;
                };
                const clickEl = (el) => {
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
                    try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                    for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0}));
                    }
                    return {text:textOf(el), cls:String(el.className||''), id:el.id||'', rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                };
                const publishBtn = document.getElementById('home-publish-btn')
                    || Array.from(document.querySelectorAll('button,[role=button],a,div,span,label')).filter(visible)
                        .find(el => /发布作品|去发布|立即发布|开始创作/.test(textOf(el)));
                return clickEl(publishBtn);
            }'''
        )
        if first:
            result["clicked"].append({"text": "发布作品", "target": first})
        await page.wait_for_timeout(1200)

        second = None
        try:
            loc = page.locator('.cheetah-popover [class*="mainEntry"][class*="news"]').first
            if await loc.count() > 0:
                await loc.scroll_into_view_if_needed(timeout=2000)
                await loc.click(timeout=3000)
                box = await loc.bounding_box()
                second = {"text": "发布图文", "cls": "locator:.cheetah-popover [class*=mainEntry][class*=news]", "id": "", "rect": box}
        except Exception as e:
            result.setdefault("errors", []).append({"step": "graphic_locator_click", "error": str(e)[:300]})

        if not second:
            try:
                loc2 = page.locator('text=发布图文').first
                if await loc2.count() > 0:
                    await loc2.scroll_into_view_if_needed(timeout=2000)
                    await loc2.click(timeout=3000, force=True)
                    box = await loc2.bounding_box()
                    second = {"text": "发布图文", "cls": "locator:text=发布图文", "id": "", "rect": box}
            except Exception as e:
                result.setdefault("errors", []).append({"step": "graphic_text_click", "error": str(e)[:300]})

        if not second:
            try:
                detail = await page.evaluate(
                    r'''() => {
                        const textOf = el => ((el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim());
                        const visible = el => {
                            if (!el) return false;
                            const r = el.getBoundingClientRect();
                            return r.width > 10 && r.height > 10 && r.x >= 0 && r.y >= 0;
                        };
                        const all = Array.from(document.querySelectorAll('button,[role=button],a,div,span,label')).filter(visible);
                        const popoverScoped = Array.from(document.querySelectorAll('.cheetah-popover [class*="mainEntry"], .cheetah-popover div, .cheetah-popover span')).filter(visible);
                        const graphic = document.querySelector('.cheetah-popover [class*="mainEntry"][class*="news"]')
                            || document.querySelector('[class*="mainEntry"][class*="news"]')
                            || popoverScoped.find(el => /发布图文/.test(textOf(el)))
                            || all.find(el => /发布图文/.test(textOf(el)))
                            || all.find(el => textOf(el) === '图文')
                            || all.find(el => /写文章|文章/.test(textOf(el)));
                        if (!graphic) return null;
                        const r = graphic.getBoundingClientRect();
                        try { graphic.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
                        try { if (typeof graphic.click === 'function') graphic.click(); } catch (_) {}
                        for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                            graphic.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0}));
                        }
                        return {text:textOf(graphic), cls:String(graphic.className||''), id:graphic.id||'', rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                    }'''
                )
                if detail:
                    second = detail
            except Exception as e:
                result.setdefault("errors", []).append({"step": "graphic_dom_click", "error": str(e)[:300]})

        if not second:
            try:
                box = await page.locator('.cheetah-popover [class*="mainEntry"][class*="news"]').first.bounding_box()
                if box:
                    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                    second = {"text": "发布图文", "cls": "mouse_click_bbox", "id": "", "rect": box}
            except Exception as e:
                result.setdefault("errors", []).append({"step": "graphic_bbox_mouse_click", "error": str(e)[:300]})

        if second:
            result["clicked"].append({"text": "发布图文", "target": second})
        await page.wait_for_timeout(2600)
        try:
            result["post_graphic_click_probe"] = await probe_editor_surface(page)
        except Exception as e:
            result.setdefault("errors", []).append({"step": "post_graphic_click_probe", "error": str(e)[:300]})
        result["final_url"] = page.url
        return bool(first or second)

    try:
        result["probe_before"] = await _probe_publish_menu()
    except Exception as e:
        result.setdefault("errors", []).append({"step": "probe_before", "error": str(e)[:300]})

    try:
        clicked_fast = await _click_publish_btn_and_graphic()
        if clicked_fast:
            if "type=news" in (page.url or ""):
                result["ok"] = True
                return result
    except Exception as e:
        result.setdefault("errors", []).append({"step": "click_publish_btn_and_graphic", "error": str(e)[:300]})

    candidates = [
        ("发布作品", "button,[role=button],a,div,span,label"),
        ("发布图文", "button,[role=button],a,div,span,label"),
        ("图文", "button,[role=button],a,div,span,label"),
        ("文章", "button,[role=button],a,div,span,label"),
        ("写文章", "button,[role=button],a,div,span,label"),
        ("去发布", "button,[role=button],a,div,span,label"),
        ("立即发布", "button,[role=button],a,div,span,label"),
        ("开始创作", "button,[role=button],a,div,span,label"),
    ]
    for text, selectors in candidates:
        try:
            clicked = await click_visible_text_by_dom(page, text, selectors, prefer_last=False)
            if clicked:
                result["clicked"].append({"text": text, "target": clicked})
                await page.wait_for_timeout(1800)
                result["final_url"] = page.url
                if text == "发布作品":
                    try:
                        second = await click_visible_text_by_dom(page, "发布图文", selectors, prefer_last=False)
                        if second:
                            result["clicked"].append({"text": "发布图文", "target": second})
                            await page.wait_for_timeout(2200)
                            result["final_url"] = page.url
                    except Exception as e:
                        result.setdefault("errors", []).append({"text": "发布图文", "error": str(e)[:300]})
                if "type=news" in (page.url or ""):
                    result["ok"] = True
                    return result
        except Exception as e:
            result.setdefault("errors", []).append({"text": text, "error": str(e)[:300]})
    result["final_url"] = page.url
    result["ok"] = "type=news" in (page.url or "")
    return result


async def safe_collect_page_state(page: Page) -> dict:
    try:
        if page.is_closed():
            return {"url": "", "title": "", "body_snippet": "", "closed": True}
    except Exception:
        pass
    try:
        return await _collect_page_state(page)
    except Exception as e:
        return {"url": getattr(page, 'url', ''), "title": "", "body_snippet": "", "error": str(e)[:500], "safe_collect_failed": True}


async def _collect_page_state(page: Page) -> dict:
    body_text = ""
    try:
        body_text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""
    probe = await probe_editor_surface(page)
    extra = await page.evaluate(
        r'''() => {
            const textOf = el => (el?.innerText || el?.value || el?.textContent || '').trim();
            const bodyText = document.body?.innerText || '';
            const actionTexts = ['发布', '继续发布', '提交发布', '预览并发布', '确认', '确定'];
            const publishCandidate = Array.from(document.querySelectorAll('button,[role=button],div,span,a,input[type=button],input[type=submit]'))
                .find(el => actionTexts.includes(textOf(el)));
            const coverConfirm = Array.from(document.querySelectorAll('button,[role=button],div,span,a'))
                .find(el => /^确定(\s*\(\d+\))?$/.test(textOf(el)));
            const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return r.width > 20 && r.height > 12 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const dialogTexts = Array.from(document.querySelectorAll('[role=dialog], .ant-modal, .bjh-dialog, .cheetah-modal, .arco-modal, .arco-drawer'))
                .filter(visible)
                .map(el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim())
                .filter(Boolean)
                .slice(0, 10);
            const blockerKeywords = ['??', '??', '??', '??', '??', '??', '??', '??', '???', '???', '??', '??'];
            const platformBlockers = dialogTexts.filter(t => blockerKeywords.some(k => t.includes(k)));
            const hasCaptcha = bodyText.includes('??????') || bodyText.includes('???????????') || location.href.includes('wappass.baidu.com') || /captcha|security.*verify|verify.*security/i.test(bodyText + ' ' + location.href);
            return {
                body_length_estimate: bodyText.length,
                has_publish_button: !!publishCandidate,
                has_cover_confirm: !!coverConfirm,
                has_submit_success_text: bodyText.includes('??????????'),
                has_view_publish_status: bodyText.includes('??????'),
                has_captcha: hasCaptcha,
                dialog_texts: dialogTexts,
                platform_blockers: platformBlockers,
            };
        }'''
    )
    return {
        "url": page.url,
        "title": await page.title(),
        "body_snippet": body_text[:5000],
        "has_dialog": await page.locator('[role="dialog"], .ant-modal, .bjh-dialog, .cheetah-modal').count(),
        "buttons": await page.evaluate(
            """() => Array.from(document.querySelectorAll('button, [role=button], input[type=button], input[type=submit], .ant-btn, .arco-btn, [class*=btn], [class*=Btn]')).map((el, i) => ({
                i,
                tag: el.tagName,
                text: (el.innerText || el.value || el.textContent || '').trim(),
                cls: String(el.className || ''),
                id: el.id || '',
                aria: el.getAttribute('aria-label'),
                disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()
            })).slice(0,300)"""
        ),
        "editor_probe": probe,
        "title_value": probe.get("titleText") or "",
        "title_count": probe.get("countText") or "",
        **extra,
    }


async def wait_editor_ready_for_import(page: Page, timeout_ms: int = 45000) -> dict:
    await page.wait_for_function(
        """() => {
            const bodyText = document.body?.innerText || '';
            const hasTitle = !!document.querySelector('[data-testid="news-title-input"] [contenteditable="true"], [data-testid="news-title-input"] input, [data-testid="news-title-input"] textarea, textarea[placeholder*="标题"], input[placeholder*="标题"], [placeholder*="标题"]');
            const hasFrame = !!document.querySelector('iframe#ueditor_0, iframe[id*="ueditor"]');
            const hasEditorCE = !!document.querySelector('[contenteditable="true"][data-placeholder*="正文"], [contenteditable="true"][aria-label*="正文"], .ProseMirror, .ql-editor, .public-DraftEditor-content [contenteditable="true"]');
            const hasEditorShell = !!document.querySelector('[class*="FeEditor"], [class*="editor"], [class*="Editor"], [data-testid*="editor"], [data-testid*="content"]');
            const hasInsert = !!document.querySelector('.FeEditorApp-_4ecaee52b311664f-entry, #edui41_state, #edui41');
            return hasTitle && (hasFrame || hasEditorCE || hasEditorShell || hasInsert || bodyText.includes('请输入正文') || bodyText.includes('添加正文'));
        }""",
        timeout=timeout_ms,
    )
    await page.wait_for_timeout(2000)
    return await probe_editor_surface(page)


async def dismiss_tours_and_overlays(page: Page) -> dict:
    result = {"steps": []}
    try:
        closed = await page.evaluate(
            r"""() => {
                const out = [];
                const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
                const visible = el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0;
                };
                const els = Array.from(document.querySelectorAll('button,[role=button],div,span'));
                const targets = els.filter(el => {
                    const t = textOf(el);
                    const cls = String(el.className || '');
                    return visible(el) && (
                        t === '我知道了' ||
                        t === '下一步' ||
                        cls.includes('cheetah-tour-close')
                    );
                });
                for (const el of targets) {
                    const r = el.getBoundingClientRect();
                    const detail = {text:textOf(el), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                    try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
                    }
                    out.push(detail);
                }
                return out;
            }"""
        )
        result["steps"].append({"name": "dismiss_overlays", "ok": True, "targets": closed})
        await page.wait_for_timeout(1200)
    except Exception as e:
        result["steps"].append({"name": "dismiss_overlays", "ok": False, "error": str(e)[:500]})
    return result


async def click_import_doc_entry(page: Page) -> dict | None:
    """Open 插入, wait for popup, then click 导入文档. Never click 视频."""

    click_insert_js = r'''() => {
        const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
        const visible = el => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0 && s.display !== 'none' && s.visibility !== 'hidden';
        };
        const fire = (el, strategy) => {
            if (!el) return null;
            try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
            const r = el.getBoundingClientRect();
            const detail = {strategy, text:textOf(el), tag:el.tagName, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, center:{x:r.x+r.width/2,y:r.y+r.height/2}};
            try { if (typeof el.click === 'function') el.click(); } catch (_) {}
            for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                try { el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:detail.center.x,clientY:detail.center.y,button:0})); } catch (_) {}
            }
            return detail;
        };
        const fixed = document.querySelector('#edui40_state > div.FeEditorApp-_4ecaee52b311664f-entry');
        if (fixed && visible(fixed)) return fire(fixed, 'fixed-insert-button');
        const all = Array.from(document.querySelectorAll('button,[role="button"],div,span,a')).filter(visible);
        const fallback = all.find(el => {
            const t = textOf(el);
            if (!t || t.length > 12) return false;
            const cls = String(el.className || '');
            return (t === '插入' || t.startsWith('插入 ')) && (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || cls.includes('entry') || cls.includes('toolbar') || cls.includes('btn'));
        }) || null;
        return fallback ? fire(fallback, 'fallback-insert-button') : null;
    }'''

    click_import_js = r'''() => {
        const textOf = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
        const visible = el => {
            if (!el) return false;
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0 && s.display !== 'none' && s.visibility !== 'hidden';
        };
        const fire = (el, strategy) => {
            if (!el) return null;
            try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
            const r = el.getBoundingClientRect();
            const detail = {strategy, text:textOf(el), tag:el.tagName, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, center:{x:r.x+r.width/2,y:r.y+r.height/2}};
            try { if (typeof el.click === 'function') el.click(); } catch (_) {}
            for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                try { el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:detail.center.x,clientY:detail.center.y,button:0})); } catch (_) {}
            }
            return detail;
        };

        const roots = Array.from(document.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-items')).filter(visible);
        const root = roots[roots.length - 1] || null;
        if (root) {
            const nth8 = root.querySelector(':scope > div:nth-child(8)') || root.children[7] || null;
            if (nth8 && visible(nth8)) {
                const t = textOf(nth8);
                if ((t === '导入文档' || t.startsWith('导入文档')) && !t.includes('视频')) {
                    return { import_doc: fire(nth8, 'visible-menu-nth8-import-doc'), roots: roots.length, rootText: textOf(root).slice(0, 200) };
                }
            }
        }

        const allRoots = Array.from(document.querySelectorAll('[role="menu"], .arco-trigger-popup, .arco-dropdown, .semi-dropdown-menu, .semi-portal, body > div')).filter(visible);
        const items = allRoots.flatMap(root => Array.from(root.querySelectorAll('.FeEditorApp-_9d63bce81e3a0b19-items > div, [role="menuitem"], li, button, div, span')).filter(visible));
        const picked = items.find(el => {
            const t = textOf(el);
            if (!t || t.length > 20 || t.includes('视频')) return false;
            return t === '导入文档' || t.startsWith('导入文档') || !!el.querySelector('.l-icon-BjhBasicDaoruwendang');
        }) || null;
        if (picked) return { import_doc: fire(picked, 'strict-text-icon-import-doc'), roots: roots.length, sampleTexts: items.map(textOf).filter(Boolean).slice(0, 30) };
        return { import_doc: {insertOnly:true, strategy:'not-found-after-wait', roots: roots.length, sampleTexts: items.map(textOf).filter(Boolean).slice(0, 50)} };
    }'''

    insert_detail = await page.evaluate(click_insert_js)
    await page.wait_for_timeout(900)
    import_detail = None
    for _ in range(6):
        import_detail = await page.evaluate(click_import_js)
        if import_detail and import_detail.get('import_doc') and not import_detail['import_doc'].get('insertOnly'):
            break
        await page.wait_for_timeout(500)
    return {"insert": insert_detail, **(import_detail or {"import_doc": {"insertOnly": True, "strategy": "no-import-detail"}})}


async def wait_import_materialized(page: Page, article: Article, timeout_ms: int = 20000, interval_ms: int = 1500) -> dict:
    result = {"ok": False, "attempts": [], "final": None}
    loops = max(1, timeout_ms // interval_ms)
    for i in range(loops):
        snap = await verify_imported_content(page, article)
        result["attempts"].append({
            "i": i + 1,
            "ok": snap.get("ok"),
            "title_ok": snap.get("title_ok"),
            "body_ok": snap.get("body_ok"),
            "word_count_ok": snap.get("word_count_ok"),
            "title_value": snap.get("title_value"),
            "word_count_text": snap.get("word_count_text"),
            "body_length": snap.get("body_length"),
        })
        if snap.get("ok"):
            result["ok"] = True
            result["final"] = snap
            return result
        await page.wait_for_timeout(interval_ms)
    result["final"] = result["attempts"][-1] if result["attempts"] else None
    return result


async def upload_word_document(page: Page, docx_path: Path, article: Article | None = None, max_attempts: int = 3) -> dict:
    """Use ?? -> ???? and upload a local Word file."""
    result = {"attempted": True, "uploaded": False, "path": str(docx_path), "steps": [], "materialized": False, "materialize_wait": None, "set_files_done": False}
    if not docx_path.exists():
        result["steps"].append({"name": "docx_file", "ok": False, "error": "file not found"})
        return result

    result["steps"].append({"name": "before_editor_ready"})
    result["steps"].append({"name": "editor_ready", "ok": True, "skipped": True, "reason": "bypassed_for_stability"})

    try:
        overlay_result = await dismiss_tours_and_overlays(page)
        result["steps"].append(overlay_result)
    except Exception as e:
        result["steps"].append({"name": "dismiss_overlays", "ok": False, "error": str(e)[:500], "ignored": True})

    for attempt in range(1, max_attempts + 1):
        clicked = None
        last_error = None
        file_input_ready = False
        try:
            probe = await page.locator(
                'input[type="file"][name="file"][accept*=".docx" i], '
                'input[type="file"][accept*=".docx" i], '
                'input[type="file"][accept*="doc" i], '
                'input[type="file"][accept*="word" i], '
                'input[type="file"][accept*="application" i], '
                'input[type="file"]:not([accept*="video" i]):not([accept*="image" i])'
            ).count()
            file_input_ready = probe > 0
            result["steps"].append({"name": "probe_file_input", "attempt": attempt, "count": probe})
        except Exception as e:
            result["steps"].append({"name": "probe_file_input", "attempt": attempt, "error": str(e)[:500]})

        file_inputs_before = []
        if not file_input_ready:
            try:
                file_inputs_before = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('input[type=file]')).map((el, idx) => ({
                        idx,
                        accept: el.getAttribute('accept') || '',
                        name: el.getAttribute('name') || '',
                        cls: String(el.className || ''),
                        outer: (el.outerHTML || '').slice(0, 300)
                    }))"""
                )
            except Exception:
                file_inputs_before = []
            try:
                result["steps"].append({"name": "before_click_import_doc", "attempt": attempt, "file_inputs_before": len(file_inputs_before)})
                async with page.expect_file_chooser(timeout=20000) as chooser_info:
                    clicked = await asyncio.wait_for(click_import_doc_entry(page), timeout=15)
                chooser = await chooser_info.value
                await chooser.set_files(str(docx_path))
                if clicked and not clicked.get("import_doc", {}).get("insertOnly"):
                    result["steps"].append({"name": "open_import_doc", "clicked": True, "attempt": attempt, "target": clicked})
                    result["steps"].append({"name": "file_chooser_set_files", "ok": True, "attempt": attempt})
                    await page.wait_for_timeout(2500)
                    result["uploaded"] = True
                    result["set_files_done"] = True
                    file_input_ready = True
                else:
                    last_error = clicked or {"error": "insertOnly"}
            except Exception as e:
                last_error = {"error": str(e)[:500], "attempt": attempt, "kind": type(e).__name__}

            if not file_input_ready:
                if not clicked or clicked.get("import_doc", {}).get("insertOnly"):
                    result["steps"].append({"name": "open_import_doc", "clicked": False, "attempt": attempt, "detail": last_error})
                    # Do not fail immediately. The editor/insert menu is flaky under concurrency; wait and retry.
                    if attempt < max_attempts:
                        try:
                            await dismiss_tours_and_overlays(page)
                        except Exception:
                            pass
                        await page.wait_for_timeout(2500 + attempt * 1500)
                        try:
                            await page.keyboard.press("Escape")
                        except Exception:
                            pass
                        continue
                    result["uploaded"] = False
                    result["materialized"] = False
                    return result

        if result.get("uploaded"):
            file_inputs_after = []
            result["steps"].append({"name": "set_input_files", "ok": True, "attempt": attempt, "method": "file_chooser"})
        else:
            try:
                file_inputs_after = await page.evaluate(
                    """() => Array.from(document.querySelectorAll('input[type=file]')).map((el, idx) => ({
                        idx,
                        accept: el.getAttribute('accept') || '',
                        name: el.getAttribute('name') || '',
                        cls: String(el.className || ''),
                        outer: (el.outerHTML || '').slice(0, 300)
                    }))"""
                )
            except Exception:
                file_inputs_after = []

            target_index = None
            before_keys = {json.dumps(x, ensure_ascii=False) for x in file_inputs_before} if file_inputs_before else set()
            for item in file_inputs_after:
                marker = json.dumps(item, ensure_ascii=False)
                accept = (item.get('accept') or '').lower()
                if marker not in before_keys and ('doc' in accept or 'word' in accept or 'application' in accept):
                    target_index = int(item.get('idx'))
                    break
            if target_index is None:
                for item in file_inputs_after:
                    accept = (item.get('accept') or '').lower()
                    if 'video' in accept or 'image' in accept:
                        continue
                    if 'doc' in accept or 'word' in accept or 'application' in accept or item.get('name') == 'file':
                        target_index = int(item.get('idx'))
                        break

            try:
                if target_index is not None:
                    locator = page.locator('input[type="file"]').nth(target_index)
                else:
                    locator = page.locator(
                        'input[type="file"][name="file"][accept*=".docx" i], '
                        'input[type="file"][accept*=".docx" i], '
                        'input[type="file"][accept*="doc" i], '
                        'input[type="file"][accept*="word" i], '
                        'input[type="file"][accept*="application" i], '
                        'input[type="file"]:not([accept*="video" i]):not([accept*="image" i])'
                    ).last
                await locator.set_input_files(str(docx_path))
                result["uploaded"] = True
                result["set_files_done"] = True
                result["steps"].append({"name": "set_input_files", "ok": True, "attempt": attempt, "target_index": target_index, "file_inputs_after": file_inputs_after})
                await page.wait_for_timeout(2500)
            except Exception as e:
                result["steps"].append({"name": "set_input_files", "ok": False, "attempt": attempt, "target_index": target_index, "error": str(e)[:500], "file_inputs_after": file_inputs_after})
                result["uploaded"] = False
                result["materialized"] = False
                return result

        try:
            verify = await page.evaluate(
                """() => ({
                    fileInputCount: Array.from(document.querySelectorAll('input[type=file]')).length,
                    bodyText: (document.body.innerText || '').slice(0, 1200),
                    dialogCount: Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="drawer"], [class*="modal"], [class*="popup"]')).length
                })"""
            )
            result["verify"] = verify
        except Exception as e:
            result["steps"].append({"name": "verify_upload", "ok": False, "attempt": attempt, "error": str(e)[:500]})

        if article is None:
            result["uploaded"] = True
            return result

        materialize = await wait_import_materialized(page, article)
        result["materialize_wait"] = materialize
        result["steps"].append({"name": "materialize_wait", "ok": materialize.get("ok"), "attempt": attempt, "final": materialize.get("final")})
        if materialize.get("ok"):
            result["uploaded"] = True
            result["materialized"] = True
            return result

        # Important: never upload the same docx again in the same editor page.
        # If materialization is slow or verification misses it, returning here prevents duplicate article content.
        result["steps"].append({"name": "stop_after_single_upload", "reason": "prevent_duplicate_docx_import"})
        return result

    return result


async def wait_import_confirm_and_click(page: Page, wait_ms: int = 12000) -> dict:
    result = {"attempted": True, "clicked": False, "steps": []}
    try:
        await page.wait_for_function(
            r"""() => Array.from(document.querySelectorAll('button,[role=button],div,span'))
                .some(el => /^确定(\s*\(\d+\))?$/.test((el.innerText || el.textContent || '').trim()))""",
            timeout=wait_ms,
        )
        result["steps"].append({"name": "wait_confirm", "ok": True})
    except Exception as e:
        result["steps"].append({"name": "wait_confirm", "ok": False, "error": str(e)[:500]})
        return result

    try:
        confirm = await page.evaluate(
            r"""() => {
                const els = Array.from(document.querySelectorAll('button, [role=button], .cheetah-btn, .bjh-btn, div, span'));
                const candidates = els.filter(el => {
                    const t = (el.innerText || el.value || el.textContent || '').trim();
                    const r = el.getBoundingClientRect();
                    return /^确定(\s*\(\d+\))?$/.test(t) && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
                }).map(el => {
                    const r = el.getBoundingClientRect();
                    const cls = String(el.className || '');
                    const score = (cls.includes('confirmBtn') ? 120 : 0) + (cls.includes('primary') ? 60 : 0) + r.y;
                    return {el, r, cls, score};
                }).sort((a, b) => b.score - a.score)[0];
                if (!candidates) return null;
                const el = candidates.el;
                const r = candidates.r;
                const detail = {
                    text: (el.innerText || el.value || el.textContent || '').trim(),
                    tag: el.tagName,
                    cls: candidates.cls,
                    rect: {x:r.x,y:r.y,w:r.width,h:r.height},
                    center: {x:r.x+r.width/2,y:r.y+r.height/2},
                };
                try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                    el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:detail.center.x,clientY:detail.center.y,button:0}));
                }
                return detail;
            }"""
        )
        if not confirm:
            result["steps"].append({"name": "confirm_import", "clicked": False, "error": "确定 button not found"})
            return result
        result["steps"].append({"name": "confirm_import", "clicked": True, "target": confirm})
        result["clicked"] = True
        await page.wait_for_timeout(5000)
    except Exception as e:
        result["steps"].append({"name": "confirm_import", "clicked": False, "error": str(e)[:500]})
    return result


async def choose_cover_from_imported_images(page: Page, image_count: int) -> dict:
    result = {"attempted": True, "image_count": image_count, "mode": "three" if image_count >= 3 else "one", "confirmed": False, "steps": []}

    if image_count <= 0:
        try:
            mode_value = "one"
            mode_label = "鍗曞浘"
            switched = await page.evaluate(
                """(modeValue) => {
                    const input = document.querySelector(`input.cheetah-radio-input[name="cover"][value="${modeValue}"]`);
                    const label = input ? input.closest('label') : null;
                    const target = label || input;
                    if (!target) return null;
                    const r = target.getBoundingClientRect();
                    if (input) {
                        input.checked = true;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    if (typeof target.click === 'function') target.click();
                    for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                        target.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                    }
                    return {
                        rect: {x:r.x,y:r.y,w:r.width,h:r.height},
                        text: (target.innerText || target.textContent || '').trim(),
                        radioState: Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked})),
                    };
                }""",
                mode_value,
            )
            result["steps"].append({"name": "switch_one", "ok": bool(switched), "target": switched, "mode_label": mode_label})
            await page.wait_for_timeout(1200)

            opened = await page.evaluate(
                """() => {
                    const item = document.querySelector('.FeEditorApp-_93c3fe2a3121c388-item');
                    if (!item) return null;
                    const key = Object.keys(item).find(k => k.startsWith('__reactProps$'));
                    const props = key ? item[key] : null;
                    const child = props?.children?.[0];
                    const open = child?.props?.open;
                    if (typeof open !== 'function') return { key, hasProps: !!props, childProps: child?.props ? Object.keys(child.props) : [] };
                    const ret = open();
                    return { key, retType: typeof ret, childProps: Object.keys(child.props || {}) };
                }"""
            )
            result["steps"].append({"name": "open_cover_picker", "ok": bool(opened), "target": opened})
            await page.wait_for_timeout(2500)

            ai_tab = await page.evaluate(
                r"""() => {
                    const el = document.getElementById('rc-tabs-0-tab-ai')
                        || Array.from(document.querySelectorAll('.cheetah-tabs-tab-btn,.cheetah-tabs-tab,[role=tab]'))
                            .find(x => {
                                const t = ((x.innerText||x.textContent||'').trim());
                                return t === 'AI封图' || t === 'AI配图';
                            });
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                    for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
                    }
                    return { text:(el.innerText||el.textContent||'').trim(), id:el.id || '', cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height} };
                }"""
            )
            result["steps"].append({"name": "open_ai_cover_tab", "ok": bool(ai_tab), "target": ai_tab})
            await page.wait_for_timeout(1500)

            trigger = await page.evaluate(
                r"""() => {
                    const textOf = el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim());
                    const visible = el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 20 && r.height > 16 && r.x >= 0 && r.y >= 0;
                    };
                    const all = Array.from(document.querySelectorAll('span,div,button,a')).filter(visible);
                    const el = document.querySelector('.FeEditorApp-_6853aa778d53acdc-theme')
                        || all.find(x => textOf(x) === '根据全文智能生成封面')
                        || all.find(x => textOf(x).includes('根据全文智能生成封面'))
                        || all.find(x => /一键智能生图/.test(textOf(x)))
                        || null;
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                    for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                        el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.width/2,clientY:r.y+r.height/2,button:0}));
                    }
                    return { text:textOf(el), cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height} };
                }"""
            )
            result["steps"].append({"name": "trigger_ai_cover_generation", "ok": bool(trigger), "target": trigger})

            confirm = None
            for idx in range(1, 7):
                await page.wait_for_timeout(10000)
                state = await page.evaluate(
                    r"""() => {
                        const bodyText = (document.body.innerText || '').slice(0, 12000);
                        const previewImgs = Array.from(document.querySelectorAll('.FeEditorApp-eb32f45bdacfe09a-container img, .FeEditorApp-_6853aa778d53acdc-right img, img'))
                            .map(img => ({src: img.src, w: img.naturalWidth || img.width || 0, h: img.naturalHeight || img.height || 0}))
                            .filter(x => !!x.src)
                            .slice(0, 12);
                        const candidates = Array.from(document.querySelectorAll('button,div,span,a')).map(el => {
                            const text = (el.innerText||el.textContent||'').trim();
                            const cls = String(el.className||'');
                            const r = el.getBoundingClientRect();
                            return { text, cls, visible: r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0, disabled: !!el.disabled, rect: {x:r.x,y:r.y,w:r.width,h:r.height} };
                        }).filter(x => /^确定(\s*\(\d+\))?$/.test(x.text));
                        return {
                            bodyText,
                            generating: /正在生成中|请稍后再试/.test(bodyText),
                            hasRetry: /重新生成/.test(bodyText),
                            previewImgs,
                            confirmCandidates: candidates.slice(0, 10),
                            confirmEnabled: candidates.some(x => x.visible && !x.disabled),
                        };
                    }"""
                )
                result["steps"].append({"name": "poll_ai_confirm", "round": idx, "state": state})
                if state.get("confirmEnabled"):
                    confirm = await page.evaluate(
                        r"""() => {
                            const candidates = Array.from(document.querySelectorAll('button,div,span,a')).map(el => {
                                const text = (el.innerText||el.textContent||'').trim();
                                const cls = String(el.className||'');
                                const r = el.getBoundingClientRect();
                                let score = 0;
                                if (/^确定(\s*\(\d+\))?$/.test(text)) score += 300;
                                if (cls.includes('confirm')) score += 100;
                                if (cls.includes('primary')) score += 50;
                                if (r.y > 300) score += 20;
                                return { el, text, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score };
                            }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 20 && x.rect.x >= 0 && x.rect.y >= 0)
                              .sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
                            const picked = candidates[0];
                            if (!picked) return null;
                            const el = picked.el;
                            const r = picked.rect;
                            try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                            for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                                el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
                            }
                            return { text:picked.text, cls:picked.cls, rect:picked.rect, score:picked.score, candidateCount:candidates.length };
                        }"""
                    )
                    break
            result["steps"].append({"name": "confirm_ai_cover", "clicked": bool(confirm), "target": confirm})
            result["confirmed"] = bool(confirm)
            if confirm:
                cover_applied = None
                for settle_round in range(1, 21):
                    await page.wait_for_timeout(3000)
                    settle = await page.evaluate(
                        r"""() => {
                            const textOf = el => (el.innerText || el.textContent || '').trim();
                            const visible = el => {
                                const r = el.getBoundingClientRect();
                                return r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
                            };
                            const bodyText = (document.body.innerText || '').slice(0, 8000);
                            const confirmBtns = Array.from(document.querySelectorAll('button,div,span,a')).filter(el => /^缂備胶铏庨崣搴ㄥ窗閺嶎厽鍋?\s*\(\d+\))?$/.test(textOf(el)) && visible(el));
                            const modalLike = Array.from(document.querySelectorAll('[role=dialog], .cheetah-modal, .cheetah-drawer, .ant-modal, .semi-modal, .FeReactApp-c27d9e2f3e73a2ac-wrap, .FeEditorApp-_6853aa778d53acdc-wrap, .FeEditorApp-e8c90bfac9d4eab4-wrap')).filter(visible);
                            const coverBlockText = bodyText.match(/闂佽崵濮崇粈浣规櫠娴犲鍋柛鈩冪懁閻掑﹤銆掑锝呬壕濠电偠鍋愬▍鎱璼\S]{0,120}/)?.[0] || '';
                            const hasAiPanelText = /AI闂佽绻愮换瀣矆娴ｈ鐟邦潡濞差亝鍊堕煫鍥ф捣缁愭梹绻涢懖鈺侇暭闁挎稒鍔欏畷鐔碱敋閸涱喚绉?\(3:2\)|闂傚倷鐒﹁ぐ鍐矓閻㈢钃熷┑鐘叉处閸嬨劑鏌ｉ弮鍌ょ劸闁诲繐娅夐梻浣告惈缁夌兘锝炴径濠勬殼濞撴埃鍋撶€规洘顨婃俊鎼佹晜閻ｅ备鍋撻鈧弻锟犲川鐎靛摜绐楅梺绋跨箲閿曘垽骞冩禒瀣亜缂佸娉曟禍锝夋煟韫囨挾绠ｇ紒鑸佃壘椤?.test(bodyText);
                            const hasAddCoverAlert = /闂佽崵濮村ú顓㈠绩闁秴閿ゅ┑鐘叉搐缁€澶愭煟濡灝鐨烘繛鍫ヤ憾濮?.test(bodyText);
                            const coverChosenHint = /闂佽崵濮崇粈浣规櫠娴犲鍋柛鈩冪懁閻掑﹤銆掑锝呬壕濠电偠鍋愬▍鎱璼\S]{0,120}(闂備礁鎼ú銈夋偤閵娿儳鏆﹂柣顒€鎽滅槐鎾诲磼濞戞艾鈷婄紓浣稿瀵煡姊绘担鐟扮祷缂佸鏁诲缁樼節閸ャ劎鍔垫繝銏ｆ硾椤戝懘顢旈〃鍌炴倵閻熺増鍟為柣鎿勭節閸┾偓?/.test(bodyText);
                            return {
                                stillHasVisibleConfirm: confirmBtns.length > 0,
                                confirmCount: confirmBtns.length,
                                modalCount: modalLike.length,
                                hasAiPanelText,
                                hasAddCoverAlert,
                                coverChosenHint,
                                coverBlockText,
                                bodyText,
                            };
                        }"""
                    )
                    result["steps"].append({"name": "post_confirm_settle_probe", "round": settle_round, "state": settle})

                    if (not settle.get("stillHasVisibleConfirm")) and (not settle.get("hasAiPanelText")) and (not settle.get("hasAddCoverAlert")):
                        cover_applied = settle
                        break

                    if settle_round in (4, 8, 12, 16) and settle.get("stillHasVisibleConfirm"):
                        retry_confirm = await page.evaluate(
                            r"""() => {
                                const textOf = el => (el.innerText || el.textContent || '').trim();
                                const visible = el => {
                                    const r = el.getBoundingClientRect();
                                    return r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
                                };
                                const candidates = Array.from(document.querySelectorAll('button,div,span,a')).map(el => {
                                    const t = textOf(el);
                                    const cls = String(el.className || '');
                                    const r = el.getBoundingClientRect();
                                    let score = 0;
                                    if (/^缂備胶铏庨崣搴ㄥ窗閺嶎厽鍋?\s*\(\d+\))?$/.test(t)) score += 400;
                                    if (cls.includes('confirm')) score += 120;
                                    if (r.y > 300) score += 30;
                                    return { el, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score };
                                }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 20 && x.rect.x >= 0 && x.rect.y >= 0)
                                  .sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
                                const picked = candidates[0];
                                if (!picked) return null;
                                const r = picked.rect;
                                try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
                                for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                                    picked.el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 }));
                                }
                                return { text:picked.t, cls:picked.cls, rect:picked.rect, score:picked.score, candidateCount:candidates.length };
                            }"""
                        )
                        result["steps"].append({"name": "retry_confirm_ai_cover", "round": settle_round, "clicked": bool(retry_confirm), "target": retry_confirm})

                if cover_applied is None:
                    cover_applied = await page.evaluate(
                        r"""() => {
                            const bodyText = (document.body.innerText || '').slice(0, 8000);
                            const visibleConfirms = Array.from(document.querySelectorAll('button,div,span,a')).filter(el => {
                                const t = (el.innerText || el.textContent || '').trim();
                                const r = el.getBoundingClientRect();
                                return /^缂備胶铏庨崣搴ㄥ窗閺嶎厽鍋?\s*\(\d+\))?$/.test(t) && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
                            }).length;
                            return {
                                bodyText,
                                hasAddCoverAlert: /闂佽崵濮村ú顓㈠绩闁秴閿ゅ┑鐘叉搐缁€澶愭煟濡灝鐨烘繛鍫ヤ憾濮?.test(bodyText),
                                hasAiPanelText: /AI闂佽绻愮换瀣矆娴ｈ鐟邦潡濞差亝鍊堕煫鍥ф捣缁愭梹绻涢懖鈺侇暭闁挎稒鍔欏畷鐔碱敋閸涱喚绉?\(3:2\)|闂傚倷鐒﹁ぐ鍐矓閻㈢钃熷┑鐘叉处閸嬨劑鏌ｉ弮鍌ょ劸闁诲繐娅夐梻浣告惈缁夌兘锝炴径濠勬殼濞撴埃鍋撶€规洘顨婃俊鎼佹晜閻ｅ备鍋撻鈧弻锟犲川鐎靛摜绐楅梺绋跨箲閿曘垽骞冩禒瀣亜缂佸娉曟禍锝夋煟韫囨挾绠ｇ紒鑸佃壘椤?.test(bodyText),
                                visibleConfirms,
                            };
                        }"""
                    )
                result["steps"].append({"name": "verify_ai_cover_applied", "state": cover_applied})
                result["confirmed"] = bool(confirm) and (not cover_applied.get("hasAddCoverAlert")) and (not cover_applied.get("hasAiPanelText"))
            await page.wait_for_timeout(3000)
            return result
        except Exception as e:
            result["steps"].append({"name": "ai_cover_flow", "ok": False, "error": str(e)[:500]})
            return result

    try:
        mode_value = "three" if image_count >= 3 else "one"
        mode_label = "涓夊浘" if image_count >= 3 else "鍗曞浘"
        switched = await page.evaluate(
            """(modeValue) => {
                const input = document.querySelector(`input.cheetah-radio-input[name="cover"][value="${modeValue}"]`);
                const label = input ? input.closest('label') : null;
                const target = label || input;
                if (!target) return null;
                const r = target.getBoundingClientRect();
                if (input) {
                    input.checked = true;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
                if (typeof target.click === 'function') target.click();
                for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                    target.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                }
                return {
                    rect: {x:r.x,y:r.y,w:r.width,h:r.height},
                    text: (target.innerText || target.textContent || '').trim(),
                    radioState: Array.from(document.querySelectorAll('input.cheetah-radio-input[name="cover"]')).map(el => ({value:el.value, checked:el.checked})),
                };
            }""",
            mode_value,
        )
        result["steps"].append({"name": f"switch_{mode_value}", "ok": bool(switched), "target": switched, "mode_label": mode_label})
        await page.wait_for_timeout(1200)
    except Exception as e:
        result["steps"].append({"name": "switch_mode", "ok": False, "error": str(e)[:500]})
        return result

    try:
        opened = await page.evaluate(
            """() => {
                const item = document.querySelector('.FeEditorApp-_93c3fe2a3121c388-item');
                if (!item) return null;
                const key = Object.keys(item).find(k => k.startsWith('__reactProps$'));
                const props = key ? item[key] : null;
                const child = props?.children?.[0];
                const open = child?.props?.open;
                if (typeof open !== 'function') return { key, hasProps: !!props, childProps: child?.props ? Object.keys(child.props) : [] };
                const ret = open();
                return { key, retType: typeof ret, childProps: Object.keys(child.props || {}) };
            }"""
        )
        result["steps"].append({"name": "open_cover_picker", "ok": bool(opened), "target": opened})
        await page.wait_for_timeout(2500)
    except Exception as e:
        result["steps"].append({"name": "open_cover_picker", "ok": False, "error": str(e)[:500]})
        return result

    try:
        wanted = 3 if image_count >= 3 else 1
        picked = await page.evaluate(
            r"""(wanted) => {
                const checks = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => {
                    const wrap = el.closest('label,div,span,li') || el;
                    const r = wrap.getBoundingClientRect();
                    return { i, el, wrap, checked: !!el.checked, disabled: !!el.disabled, rect: {x:r.x,y:r.y,w:r.width,h:r.height}, text: (wrap.innerText || wrap.textContent || '').trim().slice(0, 100), cls: String(wrap.className || '') };
                }).filter(x => !x.disabled && x.rect.w > 5 && x.rect.h > 5);
                const checkedBefore = checks.filter(x => x.checked).map(x => x.i);
                const need = Math.max(0, wanted - checkedBefore.length);
                const clicked = [];
                for (const item of checks.filter(x => !x.checked).sort((a,b) => a.rect.y - b.rect.y || a.rect.x - b.rect.x).slice(0, need)) {
                    const r = item.rect;
                    try { if (typeof item.wrap.click === 'function') item.wrap.click(); } catch (_) {}
                    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                        item.wrap.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 }));
                    }
                    clicked.push({i:item.i, text:item.text, cls:item.cls, rect:item.rect});
                }
                const checkedAfter = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el, i) => ({ i, checked: !!el.checked, disabled: !!el.disabled }));
                const confirmTexts = Array.from(document.querySelectorAll('button,[role=button],div,span,a')).map(el => {
                    const t = (el.innerText || el.textContent || '').trim();
                    const r = el.getBoundingClientRect();
                    return { t, cls: String(el.className || ''), rect: {x:r.x,y:r.y,w:r.width,h:r.height} };
                }).filter(x => /^确定(\s*\(\d+\))?$/.test(x.t) || x.t === '取消').slice(0, 20);
                return { checkedBefore, clicked, checkedAfter, confirmTexts };
            }""",
            wanted,
        )
        result["steps"].append({"name": "pick_cover_images", "ok": True, "picked": picked})
        await page.wait_for_timeout(1200)
    except Exception as e:
        result["steps"].append({"name": "pick_cover_images", "ok": False, "error": str(e)[:500]})
        return result

    try:
        confirm = await page.evaluate(
            r"""() => {
                const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
                const candidates = els.map(el => {
                    const t = (el.innerText || el.textContent || '').trim();
                    const cls = String(el.className || '');
                    const r = el.getBoundingClientRect();
                    let score = 0;
                    if (/^确定(\s*\(\d+\))?$/.test(t)) score += 400;
                    if (cls.includes('confirmBtn')) score += 120;
                    if (cls.includes('primary')) score += 60;
                    return { el, t, cls, rect: {x:r.x,y:r.y,w:r.width,h:r.height}, score };
                }).filter(x => x.score > 0 && x.rect.w > 20 && x.rect.h > 20 && x.rect.x >= 0 && x.rect.y >= 0)
                  .sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
                const picked = candidates[0];
                if (!picked) return null;
                const r = picked.rect;
                try { if (typeof picked.el.click === 'function') picked.el.click(); } catch (_) {}
                for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                    picked.el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 }));
                }
                return { text: picked.t, cls: picked.cls, rect: picked.rect, score: picked.score };
            }"""
        )
        result["steps"].append({"name": "confirm_cover", "clicked": bool(confirm), "target": confirm})
        result["confirmed"] = bool(confirm)
        await page.wait_for_timeout(3000)
        if confirm:
            await _handle_cover_crop_processing_after_confirm(page, result)
    except Exception as e:
        result["steps"].append({"name": "confirm_cover", "clicked": False, "error": str(e)[:500]})

    return result



async def _handle_cover_crop_processing_after_confirm(page: Page, result: dict) -> None:
    """If platform says cover crop is still processing, wait/retry; after several rounds click second image."""
    switched_second = False
    for round_no in range(1, 13):
        state = await page.evaluate(
            r"""() => {
                const bodyText = (document.body.innerText || '').replace(/\s+/g, ' ').trim();
                const processing = bodyText.includes('???????') || bodyText.includes('??????') || bodyText.includes('????????');
                const confirms = Array.from(document.querySelectorAll('button,[role=button],div,span,a')).map(el => {
                    const t = (el.innerText || el.textContent || '').trim();
                    const r = el.getBoundingClientRect();
                    return {text:t, cls:String(el.className||''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}, disabled:!!el.disabled || el.getAttribute('aria-disabled') === 'true'};
                }).filter(x => /^??(\s*\(\d+\))?$/.test(x.text) && x.rect.w > 20 && x.rect.h > 20 && x.rect.x >= 0 && x.rect.y >= 0);
                return {processing, confirms, body_snippet: bodyText.slice(0,500)};
            }"""
        )
        result["steps"].append({"name":"cover_crop_processing_probe","round":round_no,"state":state})
        if not state.get("processing"):
            return
        await page.wait_for_timeout(2500)
        if round_no >= 4 and not switched_second:
            clicked_second = await page.evaluate(
                r"""() => {
                    const checks = Array.from(document.querySelectorAll('input.cheetah-checkbox-input[type="checkbox"]')).map((el,i)=>{
                        const wrap = el.closest('label,div,span,li') || el;
                        const r = wrap.getBoundingClientRect();
                        return {i,el,wrap,checked:!!el.checked,disabled:!!el.disabled,rect:{x:r.x,y:r.y,w:r.width,h:r.height},text:(wrap.innerText||wrap.textContent||'').trim().slice(0,100)};
                    }).filter(x=>!x.disabled && x.rect.w>5 && x.rect.h>5).sort((a,b)=>a.rect.y-b.rect.y||a.rect.x-b.rect.x);
                    const item = checks[1] || checks[0];
                    if (!item) return null;
                    const r=item.rect;
                    try { if (typeof item.wrap.click === 'function') item.wrap.click(); } catch(_) {}
                    for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) item.wrap.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
                    return {i:item.i,text:item.text,rect:item.rect};
                }"""
            )
            result["steps"].append({"name":"cover_crop_switch_second_image","clicked":bool(clicked_second),"target":clicked_second})
            switched_second = True
            await page.wait_for_timeout(1000)
        retry = await page.evaluate(
            r"""() => {
                const els = Array.from(document.querySelectorAll('button,[role=button],div,span,a'));
                const candidates = els.map(el=>{
                    const t=(el.innerText||el.textContent||'').trim(); const cls=String(el.className||''); const r=el.getBoundingClientRect(); let score=0;
                    if (/^??(\s*\(\d+\))?$/.test(t)) score += 400; if (cls.includes('confirmBtn')) score += 120; if (cls.includes('primary')) score += 60;
                    return {el,t,cls,rect:{x:r.x,y:r.y,w:r.width,h:r.height},score,disabled:!!el.disabled||el.getAttribute('aria-disabled')==='true'};
                }).filter(x=>x.score>0&&!x.disabled&&x.rect.w>20&&x.rect.h>20&&x.rect.x>=0&&x.rect.y>=0).sort((a,b)=>b.score-a.score||b.rect.y-a.rect.y);
                const picked=candidates[0]; if(!picked) return null; const r=picked.rect;
                try { if (typeof picked.el.click === 'function') picked.el.click(); } catch(_) {}
                for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) picked.el.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,clientX:r.x+r.w/2,clientY:r.y+r.h/2,button:0}));
                return {text:picked.t,cls:picked.cls,rect:picked.rect};
            }"""
        )
        result["steps"].append({"name":"cover_crop_retry_confirm","round":round_no,"clicked":bool(retry),"target":retry})
        if retry:
            result["confirmed"] = True
            await page.wait_for_timeout(2500)

async def _collect_cover_state(page: Page) -> dict:
    return await page.evaluate(
        r"""() => {
            const normalize = s => (s || '').replace(/\s+/g, ' ').trim();
            const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                return r.width > 6 && r.height > 6 && r.x >= 0 && r.y >= 0;
            };
            const text = (document.body?.innerText || '').slice(0, 5000);
            const coverTexts = Array.from(document.querySelectorAll('button,div,span,a')).map(el => normalize(el.innerText || el.textContent || '')).filter(Boolean);
            const coverImages = Array.from(document.querySelectorAll('[class*=cover] img, [class*=Cover] img, img')).map(img => img.src).filter(Boolean).slice(0, 30);
            const coverBg = Array.from(document.querySelectorAll('[class*=cover], [class*=Cover]')).map(el => getComputedStyle(el).backgroundImage).filter(x => x && x !== 'none').slice(0, 30);
            const candidates = Array.from(document.querySelectorAll('button,[role=button],div,span,a,label')).filter(visible).map(el => {
                const t = normalize(el.innerText || el.textContent || '');
                const cls = String(el.className || '');
                const r = el.getBoundingClientRect();
                return {text:t, cls, tag:el.tagName, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
            }).filter(x => x.text && (x.text.includes('封面') || x.text.includes('AI') || x.text.includes('生成') || x.text.includes('编辑') || x.text.includes('更换') || x.text.includes('确定') || x.text.includes('活动投稿') || x.text.includes('AIGC看文史')));
            return {
                bodyText: text,
                hasCoverDialog: Array.from(document.querySelectorAll('button,div,span')).some(el => /确定\s*\(\d+\)/.test((el.innerText || el.textContent || '').trim())),
                hasChooseCover: text.includes('选择封面'),
                hasNeedCover: text.includes('请添加封面'),
                hasEditCover: text.includes('编辑'),
                hasReplaceCover: text.includes('更换'),
                coverTexts: coverTexts.slice(0, 120),
                coverImages,
                coverBg,
                coverCandidates: candidates.slice(0, 80),
            };
        }"""
    )


async def upload_cover(page: Page, cover_path: Path) -> dict:
    """Open cover picker and upload a local cover image from docx."""
    result = {"attempted": True, "uploaded": False, "path": str(cover_path), "steps": []}
    if not cover_path.exists():
        result["steps"].append({"name": "cover_file", "ok": False, "error": "file not found"})
        return result

    try:
        clicked = await click_visible_text_by_dom(page, "选择封面", "button,[role=button],div,span,a")
        if not clicked:
            raise RuntimeError("选择封面 entry not found")
        result["steps"].append({"name": "choose_cover", "clicked": True, "target": clicked})
        await page.wait_for_timeout(1500)
    except Exception as e:
        result["steps"].append({"name": "choose_cover", "clicked": False, "error": str(e)[:500]})
        return result

    try:
        upload_input = page.locator('input[type="file"][accept*="image"]').last
        await upload_input.set_input_files(str(cover_path))
        result["steps"].append({"name": "set_input_files", "ok": True})
        await page.wait_for_timeout(6000)
        result["uploaded"] = True
    except Exception as e:
        result["steps"].append({"name": "set_input_files", "ok": False, "error": str(e)[:500]})
        return result

    try:
        confirm = await page.evaluate(
            r"""() => {
                const els = Array.from(document.querySelectorAll('button, [role=button], .cheetah-btn, .bjh-btn'));
                const candidates = els.filter(el => {
                    const t = (el.innerText || el.value || el.textContent || '').trim();
                    const r = el.getBoundingClientRect();
                    return /^确定(\s*\(\d+\))?$/.test(t) && r.width > 20 && r.height > 20 && r.x >= 0 && r.y >= 0;
                }).map(el => {
                    const r = el.getBoundingClientRect();
                    const cls = String(el.className || '');
                    const score = (cls.includes('confirmBtn') ? 100 : 0) + (cls.includes('primary') ? 50 : 0) + r.y;
                    return {el, r, cls, score};
                }).sort((a, b) => b.score - a.score)[0];
                if (!candidates) return null;
                const el = candidates.el;
                const r = candidates.r;
                const detail = {
                    text: (el.innerText || el.value || el.textContent || '').trim(),
                    tag: el.tagName,
                    cls: candidates.cls,
                    rect: {x:r.x,y:r.y,w:r.width,h:r.height},
                    center: {x:r.x+r.width/2,y:r.y+r.height/2},
                };
                try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                    el.dispatchEvent(new MouseEvent(type, {bubbles:true,cancelable:true,view:window,clientX:detail.center.x,clientY:detail.center.y,button:0}));
                }
                return detail;
            }"""
        )
        if confirm:
            result["steps"].append({"name": "confirm_cover", "clicked": True, "target": confirm})
            await page.wait_for_timeout(3000)
        else:
            result["steps"].append({"name": "confirm_cover", "clicked": False, "error": "确定/确定(n) button not found"})
    except Exception as e:
        result["steps"].append({"name": "confirm_cover", "clicked": False, "error": str(e)[:500]})

    try:
        state = await _collect_cover_state(page)
        result["verify"] = state
        strong_cover_signal = any([
            state.get('hasEditCover'),
            state.get('hasReplaceCover'),
            bool(state.get('coverBg')),
        ])
        result["confirmed"] = bool(strong_cover_signal)
    except Exception as e:
        result["steps"].append({"name": "verify_cover", "ok": False, "error": str(e)[:500]})

    return result


async def generate_ai_cover(page: Page) -> dict:
    """For no-image articles: open real cover panel, click AI封图, then click 根据全文智能生成封面, and only observe state."""
    result = {"attempted": True, "generated": False, "confirmed": False, "mode": "ai", "steps": []}

    try:
        initial = await _collect_cover_state(page)
        if (initial.get("hasChooseCover") and not initial.get("hasEditCover") and not initial.get("hasReplaceCover")):
            initial["hasNeedCover"] = True
        result["steps"].append({"name": "initial_cover_state", "state": initial})
    except Exception as e:
        result["steps"].append({"name": "initial_cover_state", "ok": False, "error": str(e)[:500]})

    try:
        opened = await choose_cover_from_imported_images(page, 0)
        result["steps"].append({"name": "open_cover_panel_via_react", "ok": bool(opened), "detail": opened})
        await page.wait_for_timeout(1800)
    except Exception as e:
        result["steps"].append({"name": "open_cover_panel_via_react", "ok": False, "error": str(e)[:500]})

    try:
        ai_click = await page.evaluate(
            r"""() => {
                const textOf = el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim());
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 12 && r.height > 12 && r.x >= 0 && r.y >= 0;
                };
                const el = document.getElementById('rc-tabs-0-tab-ai')
                    || Array.from(document.querySelectorAll('button,[role=tab],.cheetah-tabs-tab-btn,.cheetah-tabs-tab')).filter(visible)
                        .find(x => textOf(x) === 'AI封图');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
                try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                    el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                }
                return { text: textOf(el), id: el.id || '', cls: String(el.className || ''), rect: {x:r.x,y:r.y,w:r.width,h:r.height} };
            }"""
        )
        result["steps"].append({"name": "click_ai_cover_tab", "clicked": bool(ai_click), "target": ai_click})
        await page.wait_for_timeout(2000)
    except Exception as e:
        result["steps"].append({"name": "click_ai_cover_tab", "clicked": False, "error": str(e)[:500]})

    try:
        fulltext_click = await page.evaluate(
            r"""() => {
                const textOf = el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim());
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 12 && r.height > 12 && r.x >= 0 && r.y >= 0;
                };
                const all = Array.from(document.querySelectorAll('.FeEditorApp-_6853aa778d53acdc-theme, .FeEditorApp-_6853aa778d53acdc-left, .FeEditorApp-_6853aa778d53acdc-content, button, a, label')).filter(visible);
                const el = all.find(x => textOf(x) === '根据全文智能生成封面')
                    || all.find(x => textOf(x).includes('根据全文智能生成封面'));
                if (!el) return null;
                const r = el.getBoundingClientRect();
                try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
                try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                    el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                }
                return { text: textOf(el), cls: String(el.className || ''), rect: {x:r.x,y:r.y,w:r.width,h:r.height} };
            }"""
        )
        result["steps"].append({"name": "click_fulltext_ai_cover", "clicked": bool(fulltext_click), "target": fulltext_click})
        if fulltext_click:
            result["generated"] = True
        await page.wait_for_timeout(3000)
    except Exception as e:
        result["steps"].append({"name": "click_fulltext_ai_cover", "clicked": False, "error": str(e)[:500]})

    confirm_clicked = None
    for idx in range(1, 7):
        try:
            state = await page.evaluate(
                r"""() => {
                    const bodyText = (document.body.innerText || '').slice(0, 12000);
                    const textOf = el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim());
                    const visible = el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 12 && r.height > 12 && r.x >= 0 && r.y >= 0;
                    };
                    const actionBtns = Array.from(document.querySelectorAll('button.cheetah-btn, button, [role=button]')).filter(visible).map(el => ({
                        text: textOf(el),
                        cls: String(el.className || ''),
                        tag: el.tagName,
                        rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })(),
                    })).filter(x => /^(下一步|确定(\s*\(\d+\))?)$/.test(x.text));
                    return {
                        bodyText,
                        hasAiTab: bodyText.includes('AI封图'),
                        hasFulltextAction: bodyText.includes('根据全文智能生成封面'),
                        hasOneClickGen: bodyText.includes('一键智能生图'),
                        hasRetry: bodyText.includes('重新生成'),
                        hasChooseCover: bodyText.includes('选择封面'),
                        hasNeedCover: bodyText.includes('请添加封面'),
                        hasEdit: bodyText.includes('编辑'),
                        hasReplace: bodyText.includes('更换'),
                        actionBtns,
                    };
                }"""
            )
            result["steps"].append({"name": f"observe_ai_cover_state_{idx}", "state": state})
            if state.get("actionBtns"):
                confirm_clicked = await page.evaluate(
                    r"""() => {
                        const textOf = el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim());
                        const visible = el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 12 && r.height > 12 && r.x >= 0 && r.y >= 0;
                        };
                        const dialogRoots = Array.from(document.querySelectorAll('[role="dialog"], .cheetah-modal, .cheetah-drawer, .arco-modal, .arco-drawer')).filter(visible);
                        const scopeButtons = dialogRoots.length
                            ? dialogRoots.flatMap(root => Array.from(root.querySelectorAll('button.cheetah-btn, button, [role=button]')))
                            : Array.from(document.querySelectorAll('button.cheetah-btn, button, [role=button]'));
                        const candidates = scopeButtons.filter(visible).map(el => {
                            const t = textOf(el);
                            const cls = String(el.className || '');
                            const r = el.getBoundingClientRect();
                            let score = 0;
                            if (/^确定\s*\(\d+\)$/.test(t)) score += 1200;
                            else if (t === '确定') score += 1100;
                            else if (t === '下一步') score += 400;
                            if (el.tagName === 'BUTTON') score += 220;
                            if (cls.includes('primary')) score += 220;
                            if (cls.includes('solid')) score += 100;
                            if (cls.includes('confirm')) score += 100;
                            if (dialogRoots.length) score += 160;
                            if (r.y > 180) score += 20;
                            return { el, text:t, cls, tag: el.tagName, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score };
                        }).filter(x => x.score > 0).sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
                        const picked = candidates[0];
                        if (!picked) return null;
                        const el = picked.el;
                        const r = picked.rect;
                        try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
                        try { el.focus(); } catch (_) {}
                        try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                        try { el.dispatchEvent(new PointerEvent('pointerdown', { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 })); } catch (_) {}
                        try { el.dispatchEvent(new MouseEvent('mousedown', { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 })); } catch (_) {}
                        try { el.dispatchEvent(new PointerEvent('pointerup', { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 })); } catch (_) {}
                        try { el.dispatchEvent(new MouseEvent('mouseup', { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 })); } catch (_) {}
                        try { el.dispatchEvent(new MouseEvent('click', { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 })); } catch (_) {}
                        return { text:picked.text, cls:picked.cls, rect:picked.rect, score:picked.score, dialogScoped: dialogRoots.length > 0, dialogCount: dialogRoots.length };
                    }"""
                )
                result["steps"].append({"name": "click_ai_cover_confirm", "clicked": bool(confirm_clicked), "target": confirm_clicked, "round": idx})
                await page.wait_for_timeout(4000)
                break
        except Exception as e:
            result["steps"].append({"name": f"observe_ai_cover_state_{idx}", "ok": False, "error": str(e)[:500]})
        await page.wait_for_timeout(3000)

    for settle_idx in range(1, 7):
        try:
            verify = await _collect_cover_state(page)
            result["steps"].append({"name": f"verify_cover_applied_{settle_idx}", "state": verify})
            if verify.get("hasEditCover") or verify.get("hasReplaceCover") or verify.get("coverBg"):
                result["verify"] = verify
                result["confirmed"] = True
                return result
        except Exception as e:
            result["steps"].append({"name": f"verify_cover_applied_{settle_idx}", "ok": False, "error": str(e)[:500]})
        await page.wait_for_timeout(3000)

    try:
        result["verify"] = await _collect_cover_state(page)
    except Exception:
        pass
    result["confirmed"] = False
    return result


async def select_activities(page: Page, activity_names: list[str] | None) -> dict:
    requested = activity_names or []
    result = {"attempted": True, "requested": requested, "selected": [], "missing": [], "available": [], "fallback_used": False, "steps": []}

    try:
        await page.wait_for_timeout(1200)
        try:
            expand = await page.evaluate(
                r"""() => {
                    const normalize = s => (s || '').replace(/\s+/g, ' ').trim();
                    const textOf = el => normalize(el?.innerText || el?.textContent || '');
                    const visible = el => {
                        if (!el) return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0;
                    };
                    const all = Array.from(document.querySelectorAll('button,[role=button],a,div,span,label')).filter(visible);
                    const picked = all.find(el => textOf(el) === '活动投稿') || all.find(el => textOf(el).includes('活动投稿')) || null;
                    if (!picked) return {clicked: false};
                    const r = picked.getBoundingClientRect();
                    try { if (typeof picked.click === 'function') picked.click(); } catch (_) {}
                    for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                        picked.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                    }
                    return {clicked: true, picked: {text:textOf(picked), cls:String(picked.className || ''), rect:{x:r.x,y:r.y,w:r.width,h:r.height}}};
                }"""
            )
            result['steps'].append({'name': 'expand_activity_panel', 'ok': True, 'expand': expand})
            await page.wait_for_timeout(1800)
        except Exception as e:
            result['steps'].append({'name': 'expand_activity_panel', 'ok': False, 'error': str(e)[:500]})
    except Exception as e:
        result["steps"].append({"name": "activity_panel_prepare", "ok": False, "error": str(e)[:500]})

    try:
        picked = await page.evaluate(
            r"""(wantedNames) => {
                const normalize = s => (s || '').replace(/\s+/g, ' ').trim();
                const textOf = el => normalize(el?.innerText || el?.textContent || '');
                const wanted = (wantedNames || []).map(normalize).filter(Boolean);
                const clicked = [];
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0;
                };
                const all = Array.from(document.querySelectorAll('div,button,[role=button],span,a,label')).filter(visible);

                const activityCards = all.map(el => {
                    const t = textOf(el);
                    const cls = String(el.className || '');
                    const r = el.getBoundingClientRect();
                    return {el, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                }).filter(x => x.t && x.cls.includes('taskCard') && (x.t.includes('人参加') || x.t.includes('万人参加')) && !x.t.includes('活动投稿'));

                const available = activityCards.map(x => ({text:x.t, cls:x.cls, rect:x.rect})).slice(0, 20);

                const clickTarget = (target, nameHint) => {
                    if (!target) return false;
                    const r = target.getBoundingClientRect();
                    try { if (typeof target.click === 'function') target.click(); } catch (_) {}
                    for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                        target.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                    }
                    clicked.push({ name: nameHint || textOf(target), matchedText: textOf(target), cls: String(target.className || ''), rect: {x:r.x,y:r.y,w:r.width,h:r.height} });
                    return true;
                };

                if (wanted.length > 0) {
                    for (const name of wanted) {
                        const base = all.find(el => textOf(el) === name) || all.find(el => textOf(el).startsWith(name)) || all.find(el => textOf(el).includes(name));
                        if (base) clickTarget(base.closest('label,button,a,[role=button]') || base, name);
                    }
                } else if (activityCards.length > 0) {
                    const first = activityCards[0];
                    clickTarget(first.el.closest('label,button,a,[role=button]') || first.el, first.t);
                }

                const selectedState = all.map(el => {
                    const t = textOf(el);
                    const cls = String(el.className || '');
                    return {text:t, cls};
                }).filter(x => x.text && (x.text.includes('AIGC看文史') || x.text.includes('已参加') || x.text.includes('已选择') || x.text.includes('取消参加') || x.text.includes('人参加'))).slice(0, 40);

                return { clicked, available, selectedState };
            }""",
            activity_names,
        )
        result["selected"] = picked.get("clicked", [])
        result["available"] = picked.get("available", [])
        selected_names = {item.get("name") for item in result["selected"]}
        result["missing"] = [name for name in (activity_names or []) if name not in selected_names]
        if requested and result["missing"] and result["available"]:
            try:
                fallback = await page.evaluate(
                    r"""() => {
                        const normalize = s => (s || '').replace(/\s+/g, ' ').trim();
                        const textOf = el => normalize(el?.innerText || el?.textContent || '');
                        const visible = el => {
                            if (!el) return false;
                            const r = el.getBoundingClientRect();
                            return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0;
                        };
                        const all = Array.from(document.querySelectorAll('div,button,[role=button],span,a,label')).filter(visible);
                        const activityCards = all.map(el => {
                            const t = textOf(el);
                            const cls = String(el.className || '');
                            const r = el.getBoundingClientRect();
                            return {el, t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                        }).filter(x => x.t && x.cls.includes('taskCard') && (x.t.includes('人参加') || x.t.includes('万人参加')) && !x.t.includes('活动投稿'));
                        const first = activityCards[0];
                        if (!first) return {clicked:false};
                        const target = first.el.closest('label,button,a,[role=button]') || first.el;
                        const r = target.getBoundingClientRect();
                        try { if (typeof target.click === 'function') target.click(); } catch (_) {}
                        for (const type of ['pointerover','mouseover','mouseenter','mousemove','pointerdown','mousedown','pointerup','mouseup','click']) {
                            target.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0 }));
                        }
                        return {clicked:true, name:first.t, rect:{x:r.x,y:r.y,w:r.width,h:r.height}};
                    }"""
                )
                if fallback.get('clicked'):
                    result['fallback_used'] = True
                    result['selected'].append({'name': fallback.get('name'), 'matchedText': fallback.get('name'), 'fallback': True})
                    result['steps'].append({'name': 'fallback_first_activity', 'ok': True, 'fallback': fallback})
                    result['missing'] = []
                    await page.wait_for_timeout(1200)
            except Exception as e:
                result['steps'].append({'name': 'fallback_first_activity', 'ok': False, 'error': str(e)[:500]})
        result["steps"].append({"name": "select_activities", "ok": True, "picked": picked})
        await page.wait_for_timeout(2000)
        verify = await page.evaluate(
            r"""() => {
                const normalize = s => (s || '').replace(/\s+/g, ' ').trim();
                const visible = el => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 8 && r.height > 8 && r.x >= 0 && r.y >= 0;
                };
                const all = Array.from(document.querySelectorAll('div,button,[role=button],span,a,label')).filter(visible);
                return all.map(el => ({text: normalize(el.innerText || el.textContent || ''), cls: String(el.className || '')}))
                    .filter(x => x.text && (x.text.includes('AIGC看文史') || x.text.includes('已参加') || x.text.includes('已选择') || x.text.includes('取消参加') || x.text.includes('人参加')))
                    .slice(0, 50);
            }"""
        )
        result["steps"].append({"name": "verify_activity_state", "ok": True, "state": verify})
    except Exception as e:
        result["steps"].append({"name": "select_activities", "ok": False, "error": str(e)[:500]})

    return result


async def publish_draft(
    article: Article,
    cookies: List[CookieItem],
    user_data_dir: Path,
    url: str | None = None,
    headless: bool = False,
    submit: bool = False,
    debug_dir: Path | None = None,
    cover_path: Path | None = None,
    docx_path: Path | None = None,
    docx_image_count: int = 0,
    keep_open_on_failure: bool = False,
    keep_open_before_submit: bool = False,
    keep_open_after_success: bool = False,
    status_callback: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    wait_manual_captcha: bool = False,
    activity_names: list[str] | None = None,
) -> dict:
    url = url or DEFAULT_PUBLISH_URLS[0]
    user_data_dir.mkdir(parents=True, exist_ok=True)
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)

    def _stage_dump(name: str, payload: dict) -> None:
        if debug_dir is None:
            return
        try:
            (debug_dir / f"stage_{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    async def emit(state: str, **payload: Any) -> None:
        if status_callback is not None:
            await status_callback(state, payload)

    async def emit_browser_state(state: str, page_obj: Page | None, message: str = "") -> None:
        payload: dict[str, Any] = {"message": message} if message else {}
        try:
            if page_obj is not None and not page_obj.is_closed():
                ps = await safe_collect_page_state(page_obj)
                payload.update({
                    "page_url": ps.get("url", ""),
                    "page_title": ps.get("title", ""),
                    "browser_title": ps.get("title_value", ""),
                    "word_count": ps.get("word_count_text", ""),
                    "has_captcha": bool(ps.get("has_captcha")),
                    "platform_blockers": ps.get("platform_blockers") or [],
                    "dialogs": ps.get("dialog_texts") or [],
                    "body_snippet": str(ps.get("body_snippet") or "")[:500],
                })
        except Exception as e:
            payload["probe_error"] = str(e)[:300]
        await emit(state, **payload)

    async with async_playwright() as p:
        await emit("LAUNCHING", article_title=article.title)
        try:
            edge_executable = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
            launch_kwargs = {
                "headless": headless,
                "viewport": {"width": 1400, "height": 900},
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            if edge_executable.exists():
                launch_kwargs["executable_path"] = str(edge_executable)
            else:
                launch_kwargs["channel"] = "msedge"
            context = await p.chromium.launch_persistent_context(
                str(user_data_dir),
                **launch_kwargs,
            )
        except Exception as e:
            error_payload = {
                "stage": "launch_persistent_context",
                "error": str(e),
                "user_data_dir": str(user_data_dir),
                "headless": headless,
                "channel": "msedge",
                "edge_executable": str(edge_executable),
            }
            if debug_dir is not None:
                try:
                    (debug_dir / "launch_error.json").write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
            await emit("FAILED", reason=f"launch_failed: {e}")
            return {
                "page_state": {"url": "", "title": "", "body_snippet": "", "has_dialog": 0, "buttons": [], "title_value": "", "title_count": "", "has_publish_button": False, "has_cover_confirm": False, "body_length_estimate": 0, "has_submit_success_text": False, "has_view_publish_status": False},
                "initial_state": {"url": "", "title_value": "", "word_count_text": "", "word_count_value": 0, "has_body_placeholder": False, "has_title_placeholder": False, "has_captcha": False, "has_latest_draft": False, "is_dirty_existing_draft": False, "body_snippet": "", "notes": [f"launch failed: {e}"]},
                "cookies_injected": 0,
                "fill": {"title_filled": False, "body_filled": False, "notes": ["launch failed before fill"]},
                "import_doc": {"attempted": False, "uploaded": False, "path": str(docx_path) if docx_path else None, "steps": []},
                "import_confirm": {"attempted": False, "clicked": False, "steps": []},
                "import_verify": {"ok": False, "title_ok": False, "body_ok": False, "word_count_ok": False, "placeholder_present": None, "title_value": "", "word_count_text": "", "word_count_value": 0, "body_length": 0, "body_preview": "", "notes": [f"launch failed: {e}"]},
                "cover": {"attempted": False, "image_count": docx_image_count, "mode": "three" if docx_image_count > 1 else "single" if docx_image_count == 1 else "ai", "confirmed": False, "steps": []},
                "activity": {"attempted": False, "requested": activity_names or [], "selected": [], "missing": activity_names or [], "available": [], "steps": []},
                "submit": {"attempted": False, "clicked": False, "published": False, "success_markers": [], "steps": []},
                "published": False,
                "network_events_tail": [],
                "events_tail": [],
                "launch_error": error_payload,
            }
        _stage_dump("01_launched", {"user_data_dir": str(user_data_dir), "pages": len(context.pages)})
        injected = await inject_cookies(context, cookies)
        _stage_dump("02_cookies_injected", {"cookies_injected": injected})
        page = context.pages[0] if context.pages else await context.new_page()
        _stage_dump("03_page_ready", {"existing_pages": len(context.pages), "page_url": page.url})
        events: list[dict] = []
        responses: list[dict] = []

        async def capture_response(r):
            if not any(k in r.url for k in ["article", "publish", "draft", "bjh", "baijiahao"]):
                return
            entry = {"url": r.url, "status": r.status}
            try:
                req = r.request
                entry["method"] = req.method
                if "importDocument" in r.url:
                    entry["post_data"] = req.post_data
            except Exception:
                pass
            if "importDocument" in r.url:
                try:
                    entry["body"] = (await r.text())[:4000]
                except Exception as e:
                    entry["body_error"] = str(e)[:300]
            responses.append(entry)

        page.on("response", lambda r: asyncio.create_task(capture_response(r)))
        page.on("dialog", lambda dialog: events.append({"kind": "dialog", "type": dialog.type, "message": dialog.message}))
        page.on("framenavigated", lambda frame: events.append({"kind": "framenavigated", "url": frame.url}) if frame == page.main_frame else None)

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        _stage_dump("04_after_goto", {"url": page.url})

        async def ensure_news_editor() -> dict:
            attempts: list[dict[str, Any]] = []
            candidate_urls = [url, *DEFAULT_PUBLISH_URLS]
            seen_urls: set[str] = set()
            normalized_urls = []
            for candidate in candidate_urls:
                if candidate and candidate not in seen_urls:
                    seen_urls.add(candidate)
                    normalized_urls.append(candidate)
            _stage_dump("04a1_guard_candidates", {"normalized_urls": normalized_urls, "current_url": page.url})
            for idx, candidate in enumerate(normalized_urls, start=1):
                _stage_dump("04a2_guard_loop_enter", {"idx": idx, "candidate": candidate, "page_url": page.url if not page.is_closed() else ""})
                if idx > 1 or page.url != candidate:
                    try:
                        await page.goto(candidate, wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(2500)
                        _stage_dump("04a3_guard_goto_done", {"idx": idx, "candidate": candidate, "page_url": page.url})
                    except Exception as e:
                        attempts.append({"url": candidate, "goto_ok": False, "error": str(e)[:500]})
                        _stage_dump("04a3_guard_goto_error", {"idx": idx, "candidate": candidate, "error": str(e)[:500]})
                        continue
                try:
                    await dismiss_tours_and_overlays(page)
                    _stage_dump("04a4_guard_overlay_done", {"idx": idx, "candidate": candidate, "page_url": page.url})
                except Exception as e:
                    _stage_dump("04a4_guard_overlay_error", {"idx": idx, "candidate": candidate, "error": str(e)[:500]})
                try:
                    await page.wait_for_timeout(3500)
                    _stage_dump("04a5_guard_wait_done", {"idx": idx, "candidate": candidate, "page_url": page.url})
                except Exception as e:
                    _stage_dump("04a5_guard_wait_error", {"idx": idx, "candidate": candidate, "error": str(e)[:500]})
                home_hop = None
                if '/builder/rc/home' in (page.url or '') or '/builder/rc/article/create' in (page.url or ''):
                    try:
                        home_hop = await try_enter_news_editor_from_home(page)
                        await page.wait_for_timeout(1500)
                        _stage_dump("04a6_guard_home_hop_done", {"idx": idx, "candidate": candidate, "page_url": page.url, "home_hop": home_hop})
                    except Exception as e:
                        home_hop = {"attempted": True, "ok": False, "error": str(e)[:300], "final_url": page.url}
                        _stage_dump("04a6_guard_home_hop_error", {"idx": idx, "candidate": candidate, "page_url": page.url, "error": str(e)[:500]})
                state = {
                    "url": page.url,
                    "candidate_url": candidate,
                    "has_news_type": "type=news" in (page.url or ""),
                    "title_input_found": False,
                    "ueditor_frame_found": False,
                    "is_login_page": False,
                    "is_error_page": False,
                }
                try:
                    await page.wait_for_function(r"""() => {
                        const text = document.body?.innerText || '';
                        const hasTitle = !!document.querySelector('[data-testid="news-title-input"] [contenteditable="true"], [data-testid="news-title-input"] input, [data-testid="news-title-input"] textarea, textarea[placeholder*="标题"], input[placeholder*="标题"], [placeholder*="标题"]');
                        const hasFrame = !!document.querySelector('iframe#ueditor_0, iframe[id*="ueditor"]');
                        const hasEditorCE = !!document.querySelector('[contenteditable="true"][data-placeholder*="正文"], [contenteditable="true"][aria-label*="正文"], .ProseMirror, .ql-editor, .public-DraftEditor-content [contenteditable="true"]');
                        const hasEditorShell = !!document.querySelector('[class*="FeEditor"], [class*="editor"], [class*="Editor"], [data-testid*="editor"], [data-testid*="content"]');
                        return hasTitle || hasFrame || hasEditorCE || hasEditorShell || text.includes('请输入标题') || text.includes('请输入正文') || text.includes('封面') || text.includes('活动') || text.includes('投稿');
                    }""", timeout=12000)
                    _stage_dump("04a7_guard_wait_for_function_done", {"idx": idx, "candidate": candidate, "page_url": page.url})
                except Exception as e:
                    _stage_dump("04a7_guard_wait_for_function_error", {"idx": idx, "candidate": candidate, "page_url": page.url if not page.is_closed() else "", "error": str(e)[:500]})
                try:
                    snap = await probe_editor_surface(page)
                    _stage_dump("04a8_guard_probe_done", {"idx": idx, "candidate": candidate, "page_url": page.url, "titleFound": bool(snap.get("titleFound")), "shellReady": bool(snap.get("shellReady")), "editorReady": bool(snap.get("editorReady")), "hasUeditorFrame": bool((snap.get("bodyReadySignals") or {}).get("hasUeditorFrame"))})
                    _stage_dump("04a8_guard_probe_full", {"idx": idx, "candidate": candidate, "page_url": page.url, "snap": snap})
                    body_text = snap.get("bodyTextSnippet") or ""
                    state["title_input_found"] = bool(snap.get("titleFound"))
                    state["ueditor_frame_found"] = bool((snap.get("bodyReadySignals") or {}).get("hasUeditorFrame"))
                    state["editor_shell_found"] = bool(snap.get("shellReady"))
                    state["editor_ready_found"] = bool(snap.get("editorReady"))
                    state["editor_state"] = snap.get("state")
                    state["body_snippet"] = body_text
                    state["probe"] = snap
                    state["is_login_page"] = ('登录' in body_text) or ('账号登录' in body_text) or ('手机号' in body_text and '验证码' in body_text and not snap.get('shellReady'))
                    state["is_error_page"] = page.url.startswith('chrome-error://chromewebdata') or ('页面异常' in body_text) or ('ERR_' in body_text)
                except Exception as e:
                    state["snapshot_error"] = str(e)[:300]
                    _stage_dump("04a8_guard_probe_error", {"idx": idx, "candidate": candidate, "page_url": page.url if not page.is_closed() else "", "error": str(e)[:500]})
                if home_hop is not None:
                    state["home_hop"] = home_hop
                    state["url"] = page.url
                    state["has_news_type"] = "type=news" in (page.url or "")

                if state["has_news_type"] and not state.get("title_input_found") and not state.get("ueditor_frame_found"):
                    try:
                        graph_pick = await click_graphic_tab(page)
                        if graph_pick:
                            await page.wait_for_timeout(2200)
                            state.setdefault("actions", []).append({"step": "click_graphic_mode", "target": graph_pick, "url": page.url})
                            snap2 = await probe_editor_surface(page)
                            state["title_input_found"] = bool(snap2.get("titleFound"))
                            state["ueditor_frame_found"] = bool((snap2.get("bodyReadySignals") or {}).get("hasUeditorFrame"))
                            state["editor_shell_found"] = bool(snap2.get("shellReady"))
                            state["editor_ready_found"] = bool(snap2.get("editorReady"))
                            state["editor_state"] = snap2.get("state")
                            state["body_snippet"] = snap2.get("bodyTextSnippet") or state.get("body_snippet") or ""
                            state["probe_after_graphic_click"] = snap2
                            state["url"] = page.url
                            state["has_news_type"] = "type=news" in (page.url or "")
                    except Exception as e:
                        state.setdefault("actions", []).append({"step": "click_graphic_mode_error", "error": str(e)[:500], "url": page.url if not page.is_closed() else ""})

                shell_only = bool(
                    state.get("has_news_type")
                    and state.get("editor_shell_found")
                    and not state.get("title_input_found")
                    and not state.get("ueditor_frame_found")
                    and not state.get("editor_ready_found")
                )
                if shell_only:
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(3000)
                        state.setdefault("actions", []).append({"step": "reload_shell_only", "url": page.url})
                        snap3 = await probe_editor_surface(page)
                        state["title_input_found"] = bool(snap3.get("titleFound"))
                        state["ueditor_frame_found"] = bool((snap3.get("bodyReadySignals") or {}).get("hasUeditorFrame"))
                        state["editor_shell_found"] = bool(snap3.get("shellReady"))
                        state["editor_ready_found"] = bool(snap3.get("editorReady"))
                        state["editor_state"] = snap3.get("state")
                        state["body_snippet"] = snap3.get("bodyTextSnippet") or state.get("body_snippet") or ""
                        state["probe_after_reload"] = snap3
                        state["url"] = page.url
                        state["has_news_type"] = "type=news" in (page.url or "")
                    except Exception as e:
                        state.setdefault("actions", []).append({"step": "reload_shell_only_error", "error": str(e)[:500], "url": page.url if not page.is_closed() else ""})

                shell_only = bool(
                    state.get("has_news_type")
                    and state.get("editor_shell_found")
                    and not state.get("title_input_found")
                    and not state.get("ueditor_frame_found")
                    and not state.get("editor_ready_found")
                )
                if shell_only:
                    try:
                        second_hop = await try_enter_news_editor_from_home(page)
                        await page.wait_for_timeout(2500)
                        state.setdefault("actions", []).append({"step": "rehop_from_shell_only", "detail": second_hop, "url": page.url})
                        snap4 = await probe_editor_surface(page)
                        state["title_input_found"] = bool(snap4.get("titleFound"))
                        state["ueditor_frame_found"] = bool((snap4.get("bodyReadySignals") or {}).get("hasUeditorFrame"))
                        state["editor_shell_found"] = bool(snap4.get("shellReady"))
                        state["editor_ready_found"] = bool(snap4.get("editorReady"))
                        state["editor_state"] = snap4.get("state")
                        state["body_snippet"] = snap4.get("bodyTextSnippet") or state.get("body_snippet") or ""
                        state["probe_after_second_home_hop"] = snap4
                        state["url"] = page.url
                        state["has_news_type"] = "type=news" in (page.url or "")
                    except Exception as e:
                        state.setdefault("actions", []).append({"step": "rehop_from_shell_only_error", "error": str(e)[:500], "url": page.url if not page.is_closed() else ""})
                state["ok"] = bool(
                    state["has_news_type"]
                    and (
                        state.get("editor_ready_found")
                        or (state["title_input_found"] and state.get("editor_shell_found"))
                        or (state["title_input_found"] and state["ueditor_frame_found"])
                    )
                )
                state["shell_only_unready"] = bool(
                    state.get("has_news_type")
                    and state.get("editor_shell_found")
                    and not state.get("title_input_found")
                    and not state.get("ueditor_frame_found")
                    and not state.get("editor_ready_found")
                )
                _stage_dump("04a9_guard_attempt_state", {"idx": idx, "candidate": candidate, "ok": state["ok"], "page_url": page.url if not page.is_closed() else "", "title_input_found": state.get("title_input_found"), "ueditor_frame_found": state.get("ueditor_frame_found"), "editor_shell_found": state.get("editor_shell_found"), "editor_ready_found": state.get("editor_ready_found"), "shell_only_unready": state.get("shell_only_unready")})
                attempts.append(state)
                if state.get("shell_only_unready") and idx == 1:
                    continue
                if state["ok"]:
                    return {"ok": True, "url": page.url, "attempts": attempts, **state}
            final = attempts[-1] if attempts else {"url": page.url}
            return {"ok": False, "url": page.url, "attempts": attempts, **final}

        _stage_dump("04a_before_news_guard", {"url": page.url})
        try:
            news_guard = await ensure_news_editor()
            _stage_dump("04b_news_guard_returned", {"url": page.url if not page.is_closed() else "", "ok": bool(news_guard.get("ok")), "keys": sorted(list(news_guard.keys()))})
        except Exception as e:
            news_guard = {"ok": False, "url": page.url if not page.is_closed() else "", "exception": str(e)[:1000], "page_state": await safe_collect_page_state(page)}
            _stage_dump("04c_news_guard_exception", news_guard)
        _stage_dump("05_news_guard", news_guard)
        try:
            await emit("EDITOR_READY", page_url=page.url, news_guard_ok=bool(news_guard.get("ok")))
            await emit_browser_state("BROWSER_STATE", page, "??????")
        except Exception:
            pass

        try:
            initial_state = await inspect_editor_initial_state(page, article)
        except Exception as e:
            initial_state = {"url": page.url, "news_guard": news_guard, "probe_error": str(e)[:500]}
        initial_state["news_guard"] = news_guard
        _stage_dump("06_initial_state", initial_state)
        try:
            await emit("EDITOR_INITIAL_STATE", dirty=bool(initial_state.get("is_dirty_existing_draft")), captcha=bool(initial_state.get("has_captcha")), latest_draft=bool(initial_state.get("has_latest_draft")), title=str(initial_state.get("title_value") or ""), word_count=str(initial_state.get("word_count_text") or ""))
        except Exception:
            pass
        if not news_guard.get("ok"):
            failure_page_state = {}
            try:
                failure_page_state = await safe_collect_page_state(page)
            except Exception as e:
                failure_page_state = {"url": page.url if page else "", "collect_error": str(e)[:300]}
            await emit("FAILED", page_url=page.url, reason="unable to reach news editor")
            await context.close()
            return {
                "page_state": failure_page_state,
                "initial_state": initial_state,
                "cookies_injected": injected,
                "fill": {"title_filled": False, "body_filled": False, "notes": ["news editor guard failed"]},
                "import_doc": {"attempted": False, "uploaded": False, "path": str(docx_path) if docx_path else None, "steps": [{"name": "skipped", "reason": "news_guard_failed"}]},
                "import_confirm": {"attempted": False, "clicked": False, "steps": []},
                "import_verify": {"ok": False, "title_ok": False, "body_ok": False, "word_count_ok": False, "notes": ["news_guard_failed"]},
                "cover": {"attempted": False, "image_count": docx_image_count, "mode": "three" if docx_image_count > 1 else "single" if docx_image_count == 1 else "ai", "confirmed": False, "steps": []},
                "activity": {"attempted": False, "requested": activity_names or [], "selected": [], "missing": activity_names or [], "available": [], "steps": [{"name": "skipped", "reason": "news_guard_failed"}]},
                "submit": {"attempted": False, "clicked": False, "published": False, "success_markers": [], "steps": [{"name": "skipped", "reason": "news_guard_failed"}]},
                "published": False,
                "network_events_tail": responses[-30:],
                "events_tail": events[-30:],
            }
        fill_result = {"title_filled": False, "body_filled": False, "notes": []}
        import_result = {"attempted": False, "uploaded": False, "path": str(docx_path) if docx_path else None, "steps": []}
        import_confirm_result = {"attempted": False, "clicked": False, "steps": []}
        import_verify_result = {"ok": False, "title_ok": False, "body_ok": False, "word_count_ok": False, "notes": []}
        if docx_path is not None:
            try:
                clear_result = await clear_editor_before_import(page)
                _stage_dump("06a_clear_editor_before_import", clear_result)
            except BaseException as e:
                _stage_dump("06a_clear_editor_before_import_error", {"error": f"{type(e).__name__}: {e}"})
            _stage_dump("06b_before_import_doc", {"docx_path": str(docx_path), "url": page.url})
            try:
                import_result = await upload_word_document(page, docx_path, article)
                _stage_dump("07_import_doc", import_result)
            except BaseException as e:
                import_result = {"attempted": True, "uploaded": False, "path": str(docx_path), "steps": [{"name": "upload_word_document_exception", "error": f"{type(e).__name__}: {e}"}]}
                _stage_dump("07_import_doc_error", import_result)

            try:
                import_confirm_result = await wait_import_confirm_and_click(page)
                _stage_dump("08_import_confirm", import_confirm_result)
            except BaseException as e:
                import_confirm_result = {"attempted": True, "clicked": False, "steps": [{"name": "wait_import_confirm_exception", "error": f"{type(e).__name__}: {e}"}]}
                _stage_dump("08_import_confirm_error", import_confirm_result)

            try:
                import_verify_result = await verify_imported_content(page, article)
                _stage_dump("09_import_verify", import_verify_result)
            except BaseException as e:
                import_verify_result = {"ok": False, "title_ok": False, "body_ok": False, "word_count_ok": False, "notes": [f"verify_imported_content_exception: {type(e).__name__}: {e}"]}
                _stage_dump("09_import_verify_error", import_verify_result)

            if not import_verify_result.get("ok"):
                # Do not manually fill after a docx import attempt. The platform may have already inserted
                # part or all of the article; manual fallback can duplicate title/body in the editor.
                _stage_dump("09b_import_verify_not_ok_no_manual_fallback", {"url": page.url, "import_verify": import_verify_result, "reason": "prevent_duplicate_content"})

            try:
                await emit("DOC_VERIFY_DONE", title_ok=import_verify_result.get("title_ok"), body_ok=import_verify_result.get("body_ok"), word_count_ok=import_verify_result.get("word_count_ok"))
                await emit_browser_state("BROWSER_STATE", page, "?????????")
            except Exception:
                pass

        # Do not block publishing based on our own content verification.
        # If content/title/length is invalid, click Publish and let the platform dialog report it.
        import_ready = True
        content_probe_ready = bool(import_verify_result.get("ok")) if docx_path is not None else True
        import_verify_result["content_probe_ready"] = content_probe_ready

        cover_result = {"attempted": False, "uploaded": False, "path": str(cover_path) if cover_path else None, "steps": []}
        if cover_path is not None and import_ready:
            try:
                await emit("COVER_PROCESSING", image_count=docx_image_count)
            except Exception:
                pass
            cover_result = await upload_cover(page, cover_path)
            _stage_dump("10_cover_result", cover_result)
            try:
                await emit("COVER_DONE", image_count=docx_image_count, cover_confirmed=bool(cover_result.get("confirmed")), cover_steps=str(cover_result.get("steps", []))[-800:])
                await emit_browser_state("BROWSER_STATE", page, "?????????")
            except Exception:
                pass
        elif docx_path is not None and import_ready:
            try:
                await emit("COVER_PROCESSING", image_count=docx_image_count)
            except Exception:
                pass
            cover_result = await generate_ai_cover(page)
            _stage_dump("10_cover_result", cover_result)
            try:
                await emit("COVER_DONE", image_count=docx_image_count, cover_confirmed=bool(cover_result.get("confirmed")), cover_steps=str(cover_result.get("steps", []))[-800:])
                await emit_browser_state("BROWSER_STATE", page, "AI?????????")
            except Exception:
                pass
        elif docx_path is not None and not import_ready:
            cover_result = {"attempted": False, "skipped": True, "reason": "manual_fill_not_ready", "steps": []}

        activity_result = {"attempted": False, "requested": activity_names or [], "selected": [], "missing": [], "available": [], "steps": []}
        if import_ready:
            activity_result = await select_activities(page, activity_names)
        else:
            activity_result = {"attempted": False, "requested": activity_names or [], "selected": [], "missing": [], "available": [], "steps": [{"name": "skipped", "reason": "content_not_ready"}]}
        _stage_dump("11_activity_result", activity_result)

        async def wait_for_manual_captcha_clear() -> dict:
            last_state = {}
            for _ in range(120):
                state = await safe_collect_page_state(page)
                text = (state.get("body_snippet") or "")
                last_state = state
                if ("百度安全验证" not in text) and ("拖动左侧滑块使图片为正" not in text):
                    return {"cleared": True, "state": state}
                await page.wait_for_timeout(3000)
            return {"cleared": False, "state": last_state}

        async def ensure_ready_to_submit() -> dict:
            history = []
            for round_idx in range(1, 9):
                state = await safe_collect_page_state(page)
                text = str(state.get("body_snippet") or "")
                blockers = {
                    "need_cover": "请添加封面" in text,
                    "ai_cover_done": "图片生成完成" in text,
                    "cover_confirm": "确定 (1)" in text or "确定(1)" in text,
                    "cover_cancel": "封面预览 (3:2)" in text and "取消" in text,
                    "dialog_open": bool(state.get("has_dialog")),
                }
                history.append({"round": round_idx, "url": state.get("url"), "dialog": state.get("has_dialog"), "blockers": blockers, "body_snippet": text[:800]})
                if not any(blockers.values()):
                    return {"ready": True, "history": history, "final_state": state}

                clicked = await page.evaluate(
                    r"""() => {
                        const textOf = el => ((el.innerText||el.textContent||'').replace(/\s+/g,' ').trim());
                        const visible = el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 12 && r.height > 12 && r.x >= 0 && r.y >= 0;
                        };
                        const roots = Array.from(document.querySelectorAll('[role="dialog"], .cheetah-modal, .cheetah-drawer, .arco-modal, .arco-drawer')).filter(visible);
                        const scope = roots.length ? roots.flatMap(root => Array.from(root.querySelectorAll('button.cheetah-btn, button, [role=button]'))) : Array.from(document.querySelectorAll('button.cheetah-btn, button, [role=button]'));
                        const candidates = scope.filter(visible).map(el => {
                            const t = textOf(el);
                            const cls = String(el.className || '');
                            const r = el.getBoundingClientRect();
                            let score = 0;
                            if (/^确定\s*\(\d+\)$/.test(t)) score += 1200;
                            else if (t === '确定') score += 1100;
                            else if (t === '下一步') score += 800;
                            if (cls.includes('primary')) score += 180;
                            if (cls.includes('solid')) score += 80;
                            if (roots.length) score += 120;
                            return { el, text:t, cls, rect:{x:r.x,y:r.y,w:r.width,h:r.height}, score };
                        }).filter(x => x.score > 0).sort((a,b) => b.score - a.score || b.rect.y - a.rect.y);
                        const picked = candidates[0];
                        if (!picked) return null;
                        const el = picked.el;
                        const r = picked.rect;
                        try { el.scrollIntoView({block:'center', inline:'center'}); } catch (_) {}
                        try { el.focus(); } catch (_) {}
                        try { if (typeof el.click === 'function') el.click(); } catch (_) {}
                        for (const type of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                            try { el.dispatchEvent(new MouseEvent(type, { bubbles:true, cancelable:true, view:window, clientX:r.x+r.w/2, clientY:r.y+r.h/2, button:0 })); } catch (_) {}
                        }
                        return { text:picked.text, cls:picked.cls, rect:picked.rect, score:picked.score, dialogScoped: roots.length > 0 };
                    }"""
                )
                history.append({"round": round_idx, "action": "resolve_blocker", "clicked": clicked})
                await page.wait_for_timeout(2500)
            final_state = await safe_collect_page_state(page)
            return {"ready": False, "history": history, "final_state": final_state}

        submit_result = {"attempted": False, "clicked": False, "published": False, "success_markers": [], "steps": []}
        can_submit = True
        if submit:
            if not can_submit:
                submit_result["attempted"] = False
                submit_result["steps"].append({"name": "publish", "clicked": False, "skipped": True, "reason": "content_not_ready"})
            else:
                submit_result["attempted"] = True
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                try:
                    await page.mouse.click(40, 40)
                    await page.wait_for_timeout(300)
                except Exception:
                    pass
                try:
                    pre_submit_state = await safe_collect_page_state(page)
                    submit_result["steps"].append({"name": "pre_submit_state", "state": pre_submit_state})
                    pre_text = pre_submit_state.get("body_snippet") or ""
                    if wait_manual_captcha and ("百度安全验证" in pre_text or "拖动左侧滑块使图片为正" in pre_text):
                        await emit("WAIT_MANUAL_CAPTCHA", message="Complete Baidu captcha manually; submit will resume automatically after it clears.")
                        captcha_wait = await wait_for_manual_captcha_clear()
                        submit_result["steps"].append({"name": "manual_captcha_wait_before_submit", **captcha_wait})
                        if captcha_wait.get("cleared"):
                            await emit("READY_TO_SUBMIT", message="Captcha cleared; preparing to continue publish.")
                    await emit_browser_state("BROWSER_STATE", page, "???????")
                    ready_gate = await ensure_ready_to_submit()
                    submit_result["steps"].append({"name": "ready_to_submit_gate", **ready_gate})
                    if not ready_gate.get("ready"):
                        raise RuntimeError("submit blocked: cover/activity/dialog state not ready")
                except Exception as e:
                    submit_result["steps"].append({"name": "pre_submit_state", "error": str(e)[:500]})
                try:
                    try:
                        overlay_result = await dismiss_tours_and_overlays(page)
                        submit_result["steps"].append({"name": "dismiss_overlays_before_submit", "detail": overlay_result})
                    except Exception as e:
                        submit_result["steps"].append({"name": "dismiss_overlays_before_submit", "error": str(e)[:500]})
                    await emit("SUBMITTING", message="Clicking publish button.")
                    await emit_browser_state("BROWSER_STATE", page, "??????")
                    box = await click_footer_publish_by_dom(page)
                    if not box:
                        box = await click_visible_text_by_dom(page, "发布", "button, [role=button], .bjh-btn, .cheetah-btn, div, span, a", prefer_last=True)
                    if not box:
                        raise RuntimeError('footer publish button not found')
                    submit_result["steps"].append({"name": "publish", "selector": "footer-dom-events", "box": box, "clicked": True})
                    submit_result["clicked"] = True
                    await page.wait_for_timeout(2500)
                except Exception as e:
                    submit_result["steps"].append({"name": "publish", "selector": "dom-events", "clicked": False, "error": str(e)[:500]})

                try:
                    confirm_box = (
                        await click_visible_text_by_dom(page, "确认", "button, [role=button], .bjh-btn, .cheetah-btn")
                        or await click_visible_text_by_dom(page, "继续发布", "button, [role=button], .bjh-btn, .cheetah-btn", prefer_last=True)
                    )
                    if confirm_box:
                        submit_result["steps"].append({"name": "confirm", "selector": "dom-events", "box": confirm_box, "clicked": True})
                        await page.wait_for_timeout(5000)
                    else:
                        submit_result["steps"].append({"name": "confirm", "selector": "dom-events", "clicked": False, "error": "visible confirm/publish not found"})
                except Exception as e:
                    submit_result["steps"].append({"name": "confirm", "selector": "dom-events", "clicked": False, "error": str(e)[:500]})
                try:
                    if wait_manual_captcha:
                        state_after_submit = await safe_collect_page_state(page)
                        after_text = state_after_submit.get("body_snippet") or ""
                        if "百度安全验证" in after_text or "拖动左侧滑块使图片为正" in after_text:
                            await emit("WAIT_MANUAL_CAPTCHA", message="Baidu captcha appeared during submit; complete it manually and the script will resume automatically.")
                            captcha_wait = await wait_for_manual_captcha_clear()
                            submit_result["steps"].append({"name": "manual_captcha_wait_after_submit", **captcha_wait})
                            if captcha_wait.get("cleared"):
                                await emit("SUBMITTING", message="Captcha cleared; continuing publish result check.")
                    await emit_browser_state("BROWSER_STATE", page, "?????????")
                    post_submit_state = await safe_collect_page_state(page)
                    submit_result["steps"].append({
                        "name": "post_submit_state",
                        "url": post_submit_state.get("url"),
                        "title": post_submit_state.get("title"),
                        "has_dialog": post_submit_state.get("has_dialog"),
                        "has_submit_success_text": post_submit_state.get("has_submit_success_text"),
                        "has_view_publish_status": post_submit_state.get("has_view_publish_status"),
                    })
                    for poll_idx in range(1, 7):
                        state = await safe_collect_page_state(page)
                        text = str(state.get("body_snippet") or "")
                        url_now = str(state.get("url") or "")
                        submit_result["steps"].append({
                            "name": f"post_submit_poll_{poll_idx}",
                            "url": url_now,
                            "title": state.get("title"),
                            "has_dialog": state.get("has_dialog"),
                            "has_submit_success_text": state.get("has_submit_success_text"),
                            "has_view_publish_status": state.get("has_view_publish_status"),
                            "body_snippet": text[:800],
                        })
                        if (
                            "/builder/rc/clue" in url_now
                            or "/builder/author/content" in url_now
                            or "/builder/rc/article" in url_now
                            or "/builder/rc/edit" in url_now
                            or "查看发布状态" in text
                            or "提交成功" in text
                            or "正在审核中" in text
                            or "发布成功" in text
                            or "内容管理" in text
                            or "草稿" in text
                        ):
                            break
                        await page.wait_for_timeout(2000)
                except Exception as e:
                    submit_result["steps"].append({"name": "post_submit_state", "error": str(e)[:500]})

        _stage_dump("12_submit_result", submit_result)
        page_state = await safe_collect_page_state(page)
        _stage_dump("13_final_page_state", page_state)
        platform_blockers = list(page_state.get("platform_blockers") or []) if isinstance(page_state, dict) else []
        captcha_required = bool(page_state.get("has_captcha")) if isinstance(page_state, dict) else False
        submit_result["platform_blockers"] = platform_blockers
        submit_result["captcha_required"] = captcha_required
        if platform_blockers:
            submit_result["steps"].append({"name": "platform_blocker_dialog", "texts": platform_blockers[:3]})
        if captcha_required:
            submit_result["steps"].append({"name": "captcha_required", "message": "manual verification required"})
            try:
                await emit("WAIT_MANUAL_CAPTCHA", message="Manual verification required in browser publish window.")
            except Exception:
                pass
        success_markers: list[str] = []
        body_snippet = (page_state.get("body_snippet") or "") if isinstance(page_state, dict) else ""
        current_url = (page_state.get("url") or "") if isinstance(page_state, dict) else ""
        if "提交成功，正在审核中" in body_snippet or ("提交成功" in body_snippet and "审核" in body_snippet):
            success_markers.append("body:submitted-reviewing")
        if "查看发布状态" in body_snippet:
            success_markers.append("body:view-publish-status")
        if "发布成功" in body_snippet:
            success_markers.append("body:publish-success")
        if "正在审核中" in body_snippet:
            success_markers.append("body:reviewing")
        if "/builder/rc/clue" in current_url:
            success_markers.append("url:clue-success-page")
        if "/builder/author/content" in current_url:
            success_markers.append("url:author-content")
        for step in submit_result.get("steps", []):
            step_url = str(step.get("url") or "")
            step_text = str(step.get("body_snippet") or "")
            if "/builder/rc/clue" in step_url and "url:clue-success-page(step)" not in success_markers:
                success_markers.append("url:clue-success-page(step)")
            if "/builder/author/content" in step_url and "url:author-content(step)" not in success_markers:
                success_markers.append("url:author-content(step)")
            if step.get("has_submit_success_text") and "step:submitted-reviewing" not in success_markers:
                success_markers.append("step:submitted-reviewing")
            if step.get("has_view_publish_status") and "step:view-publish-status" not in success_markers:
                success_markers.append("step:view-publish-status")
            if "提交成功" in step_text and "step:submit-success-text" not in success_markers:
                success_markers.append("step:submit-success-text")
            if "正在审核中" in step_text and "step:reviewing-text" not in success_markers:
                success_markers.append("step:reviewing-text")
            if "发布成功" in step_text and "step:publish-success-text" not in success_markers:
                success_markers.append("step:publish-success-text")
        publish_api_seen = any(
            str(x.get("method") or "").upper() == "POST" and "/pcui/article/publish" in str(x.get("url") or "")
            for x in (responses or [])
        )
        explicit_submit = bool(submit_result.get("clicked")) or publish_api_seen or bool(success_markers)
        if publish_api_seen and "network:publish-api-post" not in success_markers:
            success_markers.append("network:publish-api-post")
        submit_result["success_markers"] = success_markers
        submit_result["published"] = bool(success_markers) and explicit_submit
        if bool(success_markers) and explicit_submit:
            await emit("SUCCESS", success_markers=' / '.join(success_markers), page_url=current_url)

        out = {
            "page_state": page_state,
            "initial_state": initial_state,
            "cookies_injected": injected,
            "fill": fill_result,
            "import_doc": import_result,
            "import_confirm": import_confirm_result,
            "import_verify": import_verify_result,
            "cover": cover_result,
            "activity": activity_result,
            "submit": submit_result,
            "published": bool(success_markers) and explicit_submit,
            "network_events_tail": responses[-30:],
            "events_tail": events[-30:],
        }
        if debug_dir is not None:
            (debug_dir / "page_state.json").write_text(json.dumps(page_state, ensure_ascii=False, indent=2), encoding="utf-8")
            (debug_dir / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                await page.screenshot(path=str(debug_dir / "after_publish.png"), full_page=True)
            except Exception:
                pass
        if not bool(success_markers):
            await emit("FAILED", page_url=current_url, reason="publish success markers not detected")
        if keep_open_after_success and bool(success_markers):
            out["kept_open_after_success"] = True
            out["hold_reason"] = "publish_succeeded_manual_debug"
            while True:
                await page.wait_for_timeout(3600000)
        if keep_open_on_failure and not bool(success_markers):
            out["kept_open_on_failure"] = True
            out["hold_reason"] = "publish_failed_manual_debug"
            while True:
                await page.wait_for_timeout(3600000)
        if keep_open_before_submit and not submit:
            out["kept_open_before_submit"] = True
            out["hold_reason"] = "pre_submit_manual_debug"
            while True:
                await page.wait_for_timeout(3600000)
        await context.close()
        return out


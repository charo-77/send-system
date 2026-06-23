from __future__ import annotations
import asyncio, json, sys, time, html, base64, mimetypes
from pathlib import Path
from zipfile import ZipFile
base=Path(r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513")
sys.path.insert(0,str(base/'src'))
from articles import list_docx, extract_docx_article
from cookies import load_cookie_file
from browser_publish import inject_cookies, DEFAULT_PUBLISH_URLS
from playwright.async_api import async_playwright
ARTICLE_DIR=Path(r"C:\Users\Administrator\Desktop\mingming\国际")

def docx_to_html(path: Path) -> str:
    from docx import Document
    doc=Document(str(path))
    # map relationship id -> media data URL
    relmap={}
    with ZipFile(path) as z:
        for rel in doc.part.rels.values():
            try:
                if 'image' in rel.target_ref:
                    name='word/'+rel.target_ref if not rel.target_ref.startswith('word/') else rel.target_ref
                    data=z.read(name)
                    mime=mimetypes.guess_type(name)[0] or 'image/png'
                    relmap[rel.rId]=f"data:{mime};base64,"+base64.b64encode(data).decode('ascii')
            except Exception:
                pass
    chunks=[]
    ns='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'
    for p in doc.paragraphs:
        parts=[]
        for run in p.runs:
            txt=run.text or ''
            if txt:
                t=html.escape(txt)
                if run.bold: t=f'<strong>{t}</strong>'
                if run.italic: t=f'<em>{t}</em>'
                parts.append(t)
            for blip in run._element.xpath('.//*[local-name()="blip"]'):
                rid=blip.get(ns)
                if rid and rid in relmap:
                    parts.append(f'<img src="{relmap[rid]}" />')
        if parts:
            chunks.append('<p>'+''.join(parts)+'</p>')
    return '\n'.join(chunks)

async def main():
    outdir=base/'debug'/'paste_probe'; outdir.mkdir(parents=True,exist_ok=True)
    docx=list_docx(ARTICLE_DIR)[0]
    article=extract_docx_article(docx)
    content_html=docx_to_html(docx)
    (outdir/'docx.html').write_text(content_html,encoding='utf-8')
    cookies=load_cookie_file(base/'ck.txt')
    async with async_playwright() as p:
        context=await p.chromium.launch_persistent_context(str(base/f'edge_profile_paste_probe_{int(time.time())}'),channel='msedge',headless=False,viewport={'width':1400,'height':900},args=['--disable-blink-features=AutomationControlled'])
        await inject_cookies(context,cookies)
        page=context.pages[0] if context.pages else await context.new_page()
        await page.goto(DEFAULT_PUBLISH_URLS[0],wait_until='domcontentloaded',timeout=60000)
        await page.wait_for_timeout(8000)
        # fill title with existing exact method inline
        title_sel='[data-testid="news-title-input"] [contenteditable="true"][data-lexical-editor="true"]'
        loc=page.locator(title_sel).first
        await loc.wait_for(timeout=30000)
        await loc.evaluate('''el => { el.focus(); const r=document.createRange(); r.selectNodeContents(el); const s=getSelection(); s.removeAllRanges(); s.addRange(r); }''')
        await page.keyboard.press('Control+A'); await page.keyboard.press('Backspace'); await page.keyboard.insert_text(article.title)
        # focus iframe body and paste HTML via ClipboardEvent
        frame_el=await page.wait_for_selector('iframe#ueditor_0',timeout=30000)
        frame=await frame_el.content_frame()
        await frame.wait_for_load_state('domcontentloaded')
        info=await frame.locator('body').first.evaluate('''(el, html) => {
            el.focus();
            const dt = new DataTransfer();
            dt.setData('text/html', html);
            dt.setData('text/plain', html.replace(/<img[^>]*>/g, '[图片]').replace(/<[^>]+>/g, '\n'));
            const ev = new ClipboardEvent('paste', {bubbles:true, cancelable:true, clipboardData: dt});
            const ok = el.dispatchEvent(ev);
            el.dispatchEvent(new InputEvent('input', {bubbles:true, cancelable:true, inputType:'insertFromPaste'}));
            return {pasteDefaultNotPrevented: ok, text: el.innerText.slice(0,200), html: el.innerHTML.slice(0,500), imgCount: el.querySelectorAll('img').length};
        }''', content_html)
        await page.wait_for_timeout(8000)
        body_text=await page.locator('body').inner_text(timeout=3000)
        frame_info=await frame.locator('body').first.evaluate('''el => ({text:el.innerText.slice(0,500), html:el.innerHTML.slice(0,1000), imgCount:el.querySelectorAll('img').length})''')
        await page.screenshot(path=str(outdir/'after_paste.png'),full_page=True)
        result={'docx':str(docx),'html_chars':len(content_html),'paste_info':info,'frame_info':frame_info,'page_text_prefix':body_text[:2000]}
        (outdir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        await context.close()
if __name__=='__main__': asyncio.run(main())

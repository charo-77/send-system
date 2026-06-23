from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / "src"))

from articles import list_docx
from cookies import load_cookie_file
from browser_publish import inject_cookies
from playwright.async_api import async_playwright

CK = base / "ck.txt"
ARTICLES = Path(r"C:\Users\Administrator\Desktop\mingming\国际")
URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1"

SCAN_JS = r'''() => {
  const rows = Array.from(document.querySelectorAll('input[type=file]')).map((el, i) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const parent = el.parentElement;
    return {
      i,
      accept: el.getAttribute('accept') || '',
      multiple: !!el.multiple,
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      rect: {x:r.x,y:r.y,w:r.width,h:r.height},
      cls: String(el.className || ''),
      id: el.id || '',
      name: el.getAttribute('name') || '',
      style: s.cssText || '',
      parentCls: String(parent?.className || ''),
      parentText: (parent?.innerText || '').slice(0, 120),
      outerHTML: (el.outerHTML || '').slice(0, 400),
    };
  });

  return {
    fileInputs: rows,
    bodyText: (document.body.innerText || '').slice(0, 4000),
    dialogs: Array.from(document.querySelectorAll('[role=dialog], [class*="dialog"], [class*="drawer"], [class*="modal"], [class*="popup"], [class*="popover"]')).map((el, i) => {
      const r = el.getBoundingClientRect();
      return {
        i,
        cls: String(el.className || '').slice(0, 120),
        txt: (el.innerText || '').slice(0, 200),
        rect: {x:r.x,y:r.y,w:r.width,h:r.height},
        visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      };
    }).filter(x => x.visible && x.rect.w > 40 && x.rect.h > 20).slice(0, 50)
  };
}'''


def looks_like_candidate(row: dict) -> bool:
    blob = ' '.join([
        row.get('accept', ''), row.get('cls', ''), row.get('id', ''), row.get('name', ''),
        row.get('parentCls', ''), row.get('parentText', ''), row.get('outerHTML', ''),
    ]).lower()
    if 'video' in blob:
        return False
    if 'image' in blob:
        return False
    if 'doc' in blob or 'word' in blob or 'application' in blob or '上传' in blob or '导入' in blob or '文档' in blob:
        return True
    # hidden generic file inputs are still worth a try if they're not obviously image/video
    return True


async def main():
    outdir = base / 'debug' / 'try_all_file_inputs'
    outdir.mkdir(parents=True, exist_ok=True)
    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(base / f'edge_profile_tryinputs_{int(time.time())}'),
            channel='msedge',
            headless=False,
            viewport={'width': 1440, 'height': 960},
            args=['--disable-blink-features=AutomationControlled'],
        )
        await inject_cookies(context, cookies)
        page = context.pages[0] if context.pages else await context.new_page()

        responses: list[dict] = []
        requests: list[dict] = []
        page.on('request', lambda r: requests.append({
            'url': r.url,
            'method': r.method,
            'resourceType': r.resource_type,
            'headers': dict(r.headers),
        }) if any(k in r.url.lower() for k in ['upload', 'import', 'doc', 'word', 'article', 'material', 'baijiahao', 'bjh']) else None)
        page.on('response', lambda r: responses.append({
            'url': r.url,
            'status': r.status,
            'headers': dict(r.headers),
        }) if any(k in r.url.lower() for k in ['upload', 'import', 'doc', 'word', 'article', 'material', 'baijiahao', 'bjh']) else None)

        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(10000)

        before = await page.evaluate(SCAN_JS)
        await page.screenshot(path=str(outdir / '01_before.png'), full_page=True)

        candidates = [row for row in before['fileInputs'] if looks_like_candidate(row)]
        result = {
            'docx': str(docx),
            'before': before,
            'candidate_count': len(candidates),
            'attempts': [],
        }

        for row in candidates:
            idx = row['i']
            before_req = len(requests)
            before_res = len(responses)
            attempt = {
                'input_index': idx,
                'meta': row,
            }
            try:
                locator = page.locator('input[type="file"]').nth(idx)
                await locator.set_input_files(str(docx), timeout=10000)
                attempt['set_input_files'] = True
            except Exception as e:
                attempt['set_input_files'] = False
                attempt['error'] = str(e)[:800]
                result['attempts'].append(attempt)
                continue

            await page.wait_for_timeout(8000)
            snap = await page.evaluate(SCAN_JS)
            attempt['after'] = snap
            attempt['new_requests'] = requests[before_req:]
            attempt['new_responses'] = responses[before_res:]
            attempt['body_has_doc_words'] = any(x in snap.get('bodyText', '') for x in ['文档', '导入', '上传', 'Word', 'doc'])
            attempt['dialog_count'] = len(snap.get('dialogs', []))

            safe_name = f"input_{idx}"
            await page.screenshot(path=str(outdir / f'02_{safe_name}.png'), full_page=True)
            result['attempts'].append(attempt)

        (outdir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({
            'candidate_count': result['candidate_count'],
            'attempt_count': len(result['attempts']),
            'successful_sets': sum(1 for a in result['attempts'] if a.get('set_input_files')),
        }, ensure_ascii=False, indent=2))
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from articles import extract_docx_article, extract_docx_images, list_docx
from browser_publish import publish_draft
from cookies import load_cookie_file
from publish_monitor import PublishMonitor
from status_labels import cn_state

SUCCESS_TEXT = "提交成功，正在审核中..."
SUCCESS_DIRNAME = "A成功发布"
FAIL_DIRNAME = "A失败发布"


@dataclass
class RowItem:
    row: int
    name: str
    ck: str


def xlsx_to_rows(path: Path, sheet_name: str | None = None) -> list[RowItem]:
    def col_index(cell_ref: str) -> int:
        letters = ''.join(ch for ch in cell_ref if ch.isalpha())
        idx = 0
        for ch in letters:
            idx = idx * 26 + (ord(ch.upper()) - 64)
        return idx

    with zipfile.ZipFile(path) as z:
        wb_xml = z.read('xl/workbook.xml').decode('utf-8', errors='ignore')
        rels_xml = z.read('xl/_rels/workbook.xml.rels').decode('utf-8', errors='ignore')
        sheets = []
        for line in wb_xml.split('<sheet '):
            if 'name=' in line and 'r:id=' in line:
                name = line.split('name="', 1)[1].split('"', 1)[0]
                rid = line.split('r:id="', 1)[1].split('"', 1)[0]
                sheets.append((name, rid))
        rel_map = {}
        for chunk in rels_xml.split('<Relationship '):
            if 'Id=' in chunk and 'Target=' in chunk:
                rid = chunk.split('Id="', 1)[1].split('"', 1)[0]
                target = chunk.split('Target="', 1)[1].split('"', 1)[0]
                rel_map[rid] = target
        if not sheets:
            raise RuntimeError('no worksheets found')
        target_sheet = None
        for name, rid in sheets:
            if sheet_name is None or name == sheet_name:
                target_sheet = rel_map[rid]
                break
        if target_sheet is None:
            raise RuntimeError(f'sheet not found: {sheet_name}')
        sheet_path = 'xl/' + target_sheet.lstrip('/')
        sheet_xml = z.read(sheet_path).decode('utf-8', errors='ignore')

        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            sst = z.read('xl/sharedStrings.xml').decode('utf-8', errors='ignore')
            for part in sst.split('<si>')[1:]:
                text = []
                for t in part.split('<t')[1:]:
                    text.append(t.split('>', 1)[1].split('</t>', 1)[0])
                shared_strings.append(''.join(text))

        rows: list[RowItem] = []
        for row_block in sheet_xml.split('<row '):
            if 'r="' not in row_block:
                continue
            row_no = int(row_block.split('r="', 1)[1].split('"', 1)[0])
            cells = {}
            for cblock in row_block.split('<c ')[1:]:
                ref = cblock.split('r="', 1)[1].split('"', 1)[0]
                idx = col_index(ref)
                t = None
                if 't="' in cblock:
                    t = cblock.split('t="', 1)[1].split('"', 1)[0]
                value = ''
                if '<v>' in cblock:
                    value = cblock.split('<v>', 1)[1].split('</v>', 1)[0]
                    if t == 's' and value.isdigit() and int(value) < len(shared_strings):
                        value = shared_strings[int(value)]
                elif '<is>' in cblock and '<t>' in cblock:
                    value = cblock.split('<t>', 1)[1].split('</t>', 1)[0]
                cells[idx] = value
            name = cells.get(1, '').strip()
            ck = cells.get(2, '').strip()
            if row_no >= 2 and ck:
                rows.append(RowItem(row=row_no, name=name, ck=ck))
        return rows


def archive_docx(src: Path, root: Path, success: bool) -> Path:
    dest_dir = root / (SUCCESS_DIRNAME if success else FAIL_DIRNAME)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        stem, suffix = src.stem, src.suffix
        i = 2
        while True:
            candidate = dest_dir / f"{stem}__{i}{suffix}"
            if not candidate.exists():
                dest = candidate
                break
            i += 1
    shutil.move(str(src), str(dest))
    return dest


def is_success(result: dict[str, Any]) -> bool:
    if bool(result.get('published')):
        return True
    page_state = result.get('page_state') or {}
    body = page_state.get('body_snippet') or ''
    return SUCCESS_TEXT in body


def classify_failure(result: dict[str, Any], article_title: str) -> str:
    page_state = result.get('page_state') or {}
    body = page_state.get('body_snippet') or ''
    url = page_state.get('url') or ''
    title_value = (page_state.get('title_value') or '').strip()
    body_len = int(page_state.get('body_length_estimate') or 0)
    has_publish = bool(page_state.get('has_publish_button'))
    has_cover_confirm = bool(page_state.get('has_cover_confirm'))

    if '/builder/rc/clue' in url or SUCCESS_TEXT in body:
        return 'success'
    if body_len == 0:
        return 'empty-editor'
    if article_title and title_value and article_title.strip() != title_value:
        return 'title-mismatch-or-state-leak'
    if has_cover_confirm:
        return 'cover-confirm-pending'
    if has_publish:
        return 'stuck-before-submit'
    return 'unknown-edit-page-stall'


async def publish_one(slot: int, docx_path: Path, ck_text: str, account_name: str, args, monitor: PublishMonitor) -> dict[str, Any]:
    article = extract_docx_article(docx_path)
    cookies = None
    attempts: list[dict[str, Any]] = []
    final_result: dict[str, Any] | None = None
    ok = False
    max_attempts = max(1, int(getattr(args, 'retries', 1)) + 1)

    monitor.update_slot(slot, cn_state('INIT'), 账号=account_name, 文章标题=article.title, 文档路径=str(docx_path), 已发布=0, 总共=1)

    for attempt in range(1, max_attempts + 1):
        work = Path(args.debug_dir) / f"slot{slot}_try{attempt}_{docx_path.stem}"
        work.mkdir(parents=True, exist_ok=True)
        ck_file = work / 'ck.txt'
        ck_file.write_text(ck_text, encoding='utf-8')
        if cookies is None:
            cookies = load_cookie_file(ck_file)
        docx_images = extract_docx_images(docx_path, work / 'covers')
        profile_dir = Path(args.profile_root) / f"slot{slot}"
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)

        async def status_callback(state: str, payload: dict[str, Any]) -> None:
            monitor.update_slot(
                slot,
                cn_state(state),
                账号=account_name,
                已发布=(1 if state == 'SUCCESS' else 0),
                总共=1,
                **payload,
            )

        result = await publish_draft(
            article=article,
            cookies=cookies,
            user_data_dir=profile_dir,
            url=args.url,
            headless=args.headless,
            submit=True,
            debug_dir=work,
            cover_path=(docx_images[0] if docx_images else None),
            docx_path=docx_path,
            docx_image_count=len(docx_images),
            keep_open_on_failure=bool(args.keep_open_on_fail),
            status_callback=status_callback,
            wait_manual_captcha=True,
            activity_names=args.activity,
        )
        final_result = result
        ok = is_success(result)
        attempt_row = {
            'attempt': attempt,
            'success': ok,
            'published': bool(result.get('published')),
            'page_url': (result.get('page_state') or {}).get('url'),
            'body_snippet': (result.get('page_state') or {}).get('body_snippet', '')[:500],
            'failure_reason': None if ok else classify_failure(result, article.title),
            'title_value': (result.get('page_state') or {}).get('title_value'),
            'title_count': (result.get('page_state') or {}).get('title_count'),
            'body_length_estimate': (result.get('page_state') or {}).get('body_length_estimate'),
            'has_publish_button': (result.get('page_state') or {}).get('has_publish_button'),
            'has_cover_confirm': (result.get('page_state') or {}).get('has_cover_confirm'),
        }
        attempts.append(attempt_row)
        if ok:
            monitor.update_slot(slot, cn_state('SUCCESS'), 账号=account_name, 已发布=1, 总共=1, 发布结果='成功', 当前页面=attempt_row.get('page_url'))
            break
        else:
            monitor.update_slot(slot, cn_state('FAILED'), 账号=account_name, 已发布=0, 总共=1, 发布结果='失败', 失败原因=attempt_row.get('failure_reason'), 当前页面=attempt_row.get('page_url'))
        await asyncio.sleep(2)

    if ok or not args.keep_open_on_fail:
        moved_to = archive_docx(docx_path, Path(args.articles), ok)
    else:
        moved_to = docx_path
    return {
        'slot': slot,
        'source': str(docx_path),
        'moved_to': str(moved_to),
        'success': ok,
        'published': bool((final_result or {}).get('published')),
        'page_url': ((final_result or {}).get('page_state') or {}).get('url'),
        'body_snippet': (((final_result or {}).get('page_state') or {}).get('body_snippet', '')[:500]),
        'failure_reason': None if ok else classify_failure((final_result or {}), article.title),
        'attempts': attempts,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description='Publish N docs in parallel using first N ck entries from xlsx B column')
    ap.add_argument('--articles', required=True)
    ap.add_argument('--xlsx', required=True)
    ap.add_argument('--sheet', default='sheet1')
    ap.add_argument('--concurrency', type=int, default=2)
    ap.add_argument('--url', default=None)
    ap.add_argument('--profile-root', default=r'D:\milu_publish_reverse_20260513\edge_profiles_multi')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--debug-dir', default=r'D:\milu_publish_reverse_20260513\debug\multi_window_test')
    ap.add_argument('--retries', type=int, default=1, help='extra retries for failed tasks')
    ap.add_argument('--keep-open-on-fail', action='store_true', help='do not archive failed docx; keep profile/debug for manual inspection')
    ap.add_argument('--activity', action='append', default=[], help='Activity name to select before publish; repeatable')
    args = ap.parse_args()

    rows = xlsx_to_rows(Path(args.xlsx), args.sheet)
    if len(rows) < args.concurrency:
        raise SystemExit(f'xlsx usable ck rows < concurrency: {len(rows)} < {args.concurrency}')
    files = [p for p in list_docx(Path(args.articles)) if SUCCESS_DIRNAME not in p.parts and FAIL_DIRNAME not in p.parts]
    if len(files) < args.concurrency:
        raise SystemExit(f'docx files < concurrency: {len(files)} < {args.concurrency}')

    monitor = PublishMonitor(Path(args.debug_dir))
    tasks = [
        publish_one(i + 1, files[i], rows[i].ck, rows[i].name or f'账号{i+1}', args, monitor)
        for i in range(args.concurrency)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary = []
    for idx, r in enumerate(results, start=1):
        if isinstance(r, Exception):
            summary.append({'slot': idx, 'success': False, 'error': str(r)})
        else:
            summary.append(r)

    out_dir = Path(args.debug_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f'summary_{args.concurrency}.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    ok_count = sum(1 for x in summary if isinstance(x, dict) and x.get('success'))
    fail_count = len(summary) - ok_count
    monitor.finish(f'本次共 {len(summary)} 路，成功 {ok_count} 路，失败 {fail_count} 路')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

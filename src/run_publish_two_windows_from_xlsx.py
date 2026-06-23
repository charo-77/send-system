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

SUCCESS_TEXT = "提交成功，正在审核中"
SUCCESS_DIRNAME = "A成功发布"
FAIL_DIRNAME = "A失败发布"


@dataclass
class RowItem:
    row: int
    name: str
    ck: str


def _xlsx_to_rows(path: Path, sheet_name: str | None = None) -> list[RowItem]:
    # Minimal xlsx reader without external deps: use the worksheet XML directly.
    # Expect simple shared strings and B column cookie. This is enough for our test file.
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
                elif '<is>' in cblock:
                    if '<t>' in cblock:
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


async def publish_one(slot: int, docx_path: Path, ck_text: str, args) -> dict[str, Any]:
    article = extract_docx_article(docx_path)
    work = Path(args.debug_dir) / f"slot{slot}_{docx_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    ck_file = work / 'ck.txt'
    ck_file.write_text(ck_text, encoding='utf-8')
    cookies = load_cookie_file(ck_file)
    docx_images = extract_docx_images(docx_path, work / 'covers')
    result = await publish_draft(
        article=article,
        cookies=cookies,
        user_data_dir=Path(args.profile_root) / f"slot{slot}",
        url=args.url,
        headless=args.headless,
        submit=True,
        debug_dir=work,
        cover_path=(docx_images[0] if docx_images else None),
        docx_path=docx_path,
        docx_image_count=len(docx_images),
        activity_names=args.activity,
    )
    ok = is_success(result)
    moved_to = archive_docx(docx_path, Path(args.articles), ok)
    out = {
        'slot': slot,
        'source': str(docx_path),
        'moved_to': str(moved_to),
        'success': ok,
        'published': bool(result.get('published')),
        'page_url': (result.get('page_state') or {}).get('url'),
        'body_snippet': (result.get('page_state') or {}).get('body_snippet', '')[:500],
    }
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description='Use first 2 ck entries from xlsx and publish 2 docs in parallel')
    ap.add_argument('--articles', required=True)
    ap.add_argument('--xlsx', required=True)
    ap.add_argument('--sheet', default=None)
    ap.add_argument('--url', default=None)
    ap.add_argument('--profile-root', default=r'D:\milu_publish_reverse_20260513\edge_profiles_two')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--debug-dir', default=r'D:\milu_publish_reverse_20260513\debug\two_window_test')
    ap.add_argument('--activity', action='append', default=[], help='Activity name to select before publish; repeatable')
    args = ap.parse_args()

    rows = _xlsx_to_rows(Path(args.xlsx), args.sheet)
    if len(rows) < 2:
        raise SystemExit('xlsx has fewer than 2 usable ck rows')
    files = [p for p in list_docx(Path(args.articles)) if SUCCESS_DIRNAME not in p.parts and FAIL_DIRNAME not in p.parts]
    if len(files) < 2:
        raise SystemExit('need at least 2 docx files')

    tasks = [
        publish_one(1, files[0], rows[0].ck, args),
        publish_one(2, files[1], rows[1].ck, args),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary = []
    for r in results:
        if isinstance(r, Exception):
            summary.append({'success': False, 'error': str(r)})
        else:
            summary.append(r)

    out_dir = Path(args.debug_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))

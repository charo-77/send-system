from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class WorkerConfig:
    row: int
    account_name: str
    worker_name: str
    ck: str
    proxy_mode: str = ""
    proxy_ip: str = ""
    proxy_port: str = ""
    proxy_username: str = ""
    proxy_password: str = ""
    group_name: str = ""
    fingerprint_id: str = ""
    fingerprint_profile: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ck_len"] = len(self.ck or "")
        data.pop("ck", None)
        return data


def _xlsx_shared_strings(z: zipfile.ZipFile) -> list[str]:
    shared_strings: list[str] = []
    if 'xl/sharedStrings.xml' not in z.namelist():
        return shared_strings
    sst = z.read('xl/sharedStrings.xml').decode('utf-8', errors='ignore')
    for part in sst.split('<si>')[1:]:
        text = []
        for t in part.split('<t')[1:]:
            text.append(t.split('>', 1)[1].split('</t>', 1)[0])
        shared_strings.append(''.join(text))
    return shared_strings


def _col_index(cell_ref: str) -> int:
    letters = ''.join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - 64)
    return idx


def _sheet_xml(z: zipfile.ZipFile, sheet_name: str | None) -> str:
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
    return z.read(sheet_path).decode('utf-8', errors='ignore')


def _parse_sheet_rows(sheet_xml: str, shared_strings: list[str]) -> list[dict[int, str]]:
    rows: list[dict[int, str]] = []
    for row_block in sheet_xml.split('<row '):
        if 'r="' not in row_block:
            continue
        row_no = int(row_block.split('r="', 1)[1].split('"', 1)[0])
        cells: dict[int, str] = {0: str(row_no)}
        for cblock in row_block.split('<c ')[1:]:
            ref = cblock.split('r="', 1)[1].split('"', 1)[0]
            idx = _col_index(ref)
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
            cells[idx] = value.strip()
        if row_no >= 1:
            rows.append(cells)
    return rows


def load_worker_configs(path: Path, sheet_name: str | None = None) -> list[WorkerConfig]:
    with zipfile.ZipFile(path) as z:
        shared_strings = _xlsx_shared_strings(z)
        sheet_xml = _sheet_xml(z, sheet_name)
        rows = _parse_sheet_rows(sheet_xml, shared_strings)

    if not rows:
        return []

    header_row = rows[0]
    headers: dict[str, int] = {}
    for col_idx, value in header_row.items():
        if col_idx == 0:
            continue
        if value:
            headers[str(value).strip()] = col_idx

    def get_cell(row: dict[int, str], name: str) -> str:
        idx = headers.get(name)
        if not idx:
            return ''
        return str(row.get(idx, '') or '').strip()

    configs: list[WorkerConfig] = []
    for row in rows[1:]:
        account_name = get_cell(row, '账号')
        ck = get_cell(row, 'CK')
        if not ck:
            continue
        worker_name = account_name or f"worker-{row.get(0, '')}"
        configs.append(
            WorkerConfig(
                row=int(row.get(0, 0) or 0),
                account_name=account_name,
                worker_name=worker_name,
                ck=ck,
                proxy_mode=get_cell(row, '代理模式'),
                proxy_ip=get_cell(row, '代理IP'),
                proxy_port=get_cell(row, '代理端口'),
                proxy_username=get_cell(row, '代理账号'),
                proxy_password=get_cell(row, '代理密码'),
                group_name=get_cell(row, '分组'),
                fingerprint_id=get_cell(row, '指纹ID'),
                fingerprint_profile=get_cell(row, '指纹浏览器') or get_cell(row, '指纹路径') or get_cell(row, '指纹配置'),
            )
        )
    return configs


def dump_worker_configs_json(path: Path, items: list[WorkerConfig]) -> None:
    payload = [
        {
            **item.to_public_dict(),
            "ck": item.ck,
        }
        for item in items
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

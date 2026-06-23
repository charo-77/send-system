import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SRC = Path(r'D:\milu_publish_reverse_20260513\CK.xlsx')
DST = Path(r'D:\milu_publish_reverse_20260513\CK_grouped_trial.xlsx')
TARGETS = {'boss', '冒菜3', '冒菜5'}
GROUP_NAME = '国际时政长文1'
NS = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

if DST.exists():
    DST.unlink()
shutil.copy2(SRC, DST)

with zipfile.ZipFile(DST, 'r') as zin:
    shared_root = ET.fromstring(zin.read('xl/sharedStrings.xml'))
    sheet_root = ET.fromstring(zin.read('xl/worksheets/sheet1.xml'))
    files = {name: zin.read(name) for name in zin.namelist() if name not in {'xl/sharedStrings.xml', 'xl/worksheets/sheet1.xml'}}

strings = []
for si in shared_root.findall('a:si', NS):
    text = ''.join(t.text or '' for t in si.findall('.//a:t', NS))
    strings.append(text)

header_map = {}
rows = sheet_root.findall('a:sheetData/a:row', NS)
if not rows:
    raise SystemExit('no rows')
for cell in rows[0].findall('a:c', NS):
    ref = cell.attrib.get('r', '')
    col = ''.join(ch for ch in ref if ch.isalpha())
    value_el = cell.find('a:v', NS)
    if cell.attrib.get('t') == 's' and value_el is not None:
        header_map[col] = strings[int(value_el.text)]

col_by_header = {v: k for k, v in header_map.items()}
account_col = col_by_header.get('账号')
group_col = col_by_header.get('分组')
if not account_col or not group_col:
    raise SystemExit(f'missing columns: {col_by_header}')

def get_string(cell):
    value_el = cell.find('a:v', NS)
    if value_el is None:
        return ''
    if cell.attrib.get('t') == 's':
        return strings[int(value_el.text)]
    return value_el.text or ''

modified = []
for row in rows[1:]:
    cells = { ''.join(ch for ch in c.attrib.get('r','') if ch.isalpha()): c for c in row.findall('a:c', NS) }
    account_cell = cells.get(account_col)
    if account_cell is None:
        continue
    account_name = get_string(account_cell).strip()
    if account_name not in TARGETS:
        continue
    strings.append(GROUP_NAME)
    idx = len(strings) - 1
    group_ref = f'{group_col}{row.attrib.get("r")}'
    group_cell = cells.get(group_col)
    if group_cell is None:
        group_cell = ET.SubElement(row, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c', {'r': group_ref, 't': 's'})
        ET.SubElement(group_cell, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
    group_cell.set('t', 's')
    group_cell.find('a:v', NS).text = str(idx)
    modified.append(account_name)

shared_root.set('count', str(len(strings)))
shared_root.set('uniqueCount', str(len(strings)))
for child in list(shared_root):
    shared_root.remove(child)
for text in strings:
    si = ET.SubElement(shared_root, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si')
    t = ET.SubElement(si, '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
    t.text = text

with zipfile.ZipFile(DST, 'w', zipfile.ZIP_DEFLATED) as zout:
    for name, data in files.items():
        zout.writestr(name, data)
    zout.writestr('xl/sharedStrings.xml', ET.tostring(shared_root, encoding='utf-8', xml_declaration=True))
    zout.writestr('xl/worksheets/sheet1.xml', ET.tostring(sheet_root, encoding='utf-8', xml_declaration=True))

print({'dst': str(DST), 'group': GROUP_NAME, 'modified': modified})

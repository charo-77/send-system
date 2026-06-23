import re

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v2.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix SVGAnimatedString className - line 173 and 218
# Replace .map(el => ({ id: el.id, cls: el.className.slice(0,80), ...
content = re.sub(
    r"cls: el\.className\.slice\(0,80\)",
    "cls: (el.className && el.className.baseVal ? el.className.baseVal : (el.className || '')).toString().slice(0, 80)",
    content
)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v2.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('done')
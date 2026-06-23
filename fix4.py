with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v3.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'print(f"[ALL METHODS] keys={Object.keys(all_methods).slice(0,20) if typeof all_methods === \'object\' else \'N/A\'}")'
new = 'print(f"[ALL METHODS] keys={list(all_methods.keys())[:20]}")'
content = content.replace(old, new)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v3.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
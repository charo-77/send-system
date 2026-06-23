with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v4.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'await new Promise(r => setTimeout(r, 500));'
new = 'await asyncio.sleep(0.5);'
content = content.replace(old, new)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v4.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v4.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'await asyncio.sleep(0.5);'
new = 'setTimeout(function(){}, 500);'
content = content.replace(old, new)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v4.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
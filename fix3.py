with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v2.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("innerText: child.innerText.trim()", "innerText: (child.innerText || '').trim()")

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v2.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
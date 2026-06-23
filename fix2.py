with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v2.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "(child.className && child.className.baseVal ? child.className.baseVal : (child.className || ))"
new_str = "(child.className && child.className.baseVal ? child.className.baseVal : (child.className || ''))"
content = content.replace(old, new_str)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_dropdown_v2.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
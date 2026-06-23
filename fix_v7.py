with open(r'D:\milu_publish_reverse_20260513\debug_insert_v7.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "state.get('mousedown_elements', []).length",
    "len(state.get('mousedown_elements', []))"
)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_v7.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
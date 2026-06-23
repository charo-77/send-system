with open(r'D:\milu_publish_reverse_20260513\debug_insert_v12.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "repr(snap.get('e43_text','')[:80])",
    "repr((snap.get('e43_text') or '')[:80])"
)
content = content.replace(
    "snap.get('e43_visible')",
    "(snap.get('e43_visible') or False)"
)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_v12.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
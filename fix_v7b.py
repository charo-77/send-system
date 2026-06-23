with open(r'D:\milu_publish_reverse_20260513\debug_insert_v7.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix remaining .length in f-strings inside page.evaluate (JS)
content = content.replace(
    "print(f\"\\n[FINAL] popups={final['popups'].length} fileInputs={final['fileInputs'].length}\")",
    "print(f\"\\n[FINAL] popups={len(final['popups'])} fileInputs={len(final['fileInputs'])}\")"
)
# Fix inside JS strings (page.evaluate) - these are JS code so .length works there
# But wait, the print is outside the JS string, in Python. So fix the final['popups'].length to len(final['popups'])

with open(r'D:\milu_publish_reverse_20260513\debug_insert_v7.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
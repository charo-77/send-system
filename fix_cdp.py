with open(r'D:\milu_publish_reverse_20260513\debug_insert_cdp.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix missing dict wrapper for Runtime.evaluate calls
content = content.replace(
    'stateful_result = await cdp.send("Runtime.evaluate", expression="""',
    'stateful_result = await cdp.send("Runtime.evaluate", {"expression": """'
)
content = content.replace(
    'react_result = await cdp.send("Runtime.evaluate", expression="""',
    'react_result = await cdp.send("Runtime.evaluate", {"expression": """'
)

with open(r'D:\milu_publish_reverse_20260513\debug_insert_cdp.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
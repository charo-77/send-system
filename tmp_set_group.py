import json
from pathlib import Path
p = Path(r'D:\milu_publish_reverse_20260513\runtime\account_manager\accounts.json')
items = json.loads(p.read_text(encoding='utf-8'))
updates = {'boss': '国际时政长文1', '冒菜3': '国际时政长文1', '冒菜5': '国际时政长文1'}
changed = []
for x in items:
    worker = x.get('worker_name')
    if worker in updates:
        x['group_name'] = updates[worker]
        changed.append((worker, x.get('group_name')))
p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
print(changed)

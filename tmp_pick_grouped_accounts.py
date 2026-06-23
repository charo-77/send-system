import json
from pathlib import Path
p = Path(r'D:\milu_publish_reverse_20260513\runtime\account_manager\accounts.json')
items = json.loads(p.read_text(encoding='utf-8'))
rows = [x for x in items if x.get('enabled') and x.get('online_status') == 'online' and x.get('group_name')]
for x in rows[:20]:
    print(f"{x['worker_name']}|{x.get('group_name','')}")

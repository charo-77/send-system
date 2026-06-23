import json
from pathlib import Path
p = Path(r'D:\milu_publish_reverse_20260513\runtime\account_manager\accounts.json')
items = json.loads(p.read_text(encoding='utf-8'))
rows = [x for x in items if x.get('enabled') and x.get('online_status') == 'online']
for x in rows[:10]:
    print(x['worker_name'])

import json
from pathlib import Path
p = Path(r'D:\milu_publish_reverse_20260513\runtime\account_manager\accounts.json')
items = json.loads(p.read_text(encoding='utf-8'))
for x in items:
    if x.get('enabled') and x.get('online_status') == 'online' and x.get('worker_name') in ['boss','冒菜3','冒菜5']:
        print(x['worker_name'], '|', x.get('group_name',''))

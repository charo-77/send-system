import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'D:\milu_publish_reverse_20260513\src')))
from account_store import load_account_records, save_account_records
p = Path(r'D:\milu_publish_reverse_20260513\runtime\account_manager\accounts.json')
items = load_account_records(p)
updates = {'boss': '国际时政长文1', '冒菜3': '国际时政长文1', '冒菜5': '国际时政长文1'}
changed = []
for item in items:
    if item.worker_name in updates:
        item.group_name = updates[item.worker_name]
        changed.append((item.worker_name, item.group_name))
save_account_records(items, p)
print(changed)

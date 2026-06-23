import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'D:\milu_publish_reverse_20260513\src')))
from account_manager_config import load_worker_configs_from_any
items = load_worker_configs_from_any(account_store_path=Path(r'D:\milu_publish_reverse_20260513\runtime\account_manager\accounts.json'))
for x in items:
    if x.worker_name in ['boss','冒菜3','冒菜5']:
        print(x.worker_name, '|', repr(getattr(x, 'group_name', '')))

from __future__ import annotations

from account_monitor import _is_valid_real_name
from account_store import DEFAULT_ACCOUNT_STORE, load_account_records, now_iso, save_account_records


def main() -> int:
    items = load_account_records(DEFAULT_ACCOUNT_STORE)
    changed = 0
    for item in items:
        if item.real_name and not _is_valid_real_name(item.real_name):
            item.real_name = ""
            item.updated_at = now_iso()
            changed += 1
    if changed:
        save_account_records(items, DEFAULT_ACCOUNT_STORE)
    print({"changed": changed, "total": len(items), "store": str(DEFAULT_ACCOUNT_STORE)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

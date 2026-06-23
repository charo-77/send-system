from __future__ import annotations

import json
from pathlib import Path

INVALID_SET = {"99+", "44", "55", "66", "77", "88"}


def is_valid_name(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if len(value) < 2 or len(value) > 24:
        return False
    if value in INVALID_SET:
        return False
    if value.isdigit():
        return False
    if value.endswith("+") and value[:-1].isdigit():
        return False
    if value.startswith("(") and value.endswith("s)"):
        return False
    if not any("\u4e00" <= ch <= "\u9fff" or ch.isalpha() for ch in value):
        return False
    return True


def main() -> int:
    repo_root = Path(r"D:\milu_publish_reverse_20260513")
    accounts_path = repo_root / "runtime" / "account_manager" / "accounts.json"
    state_path = repo_root / "runtime" / "account_manager" / "browser_workspace_state.json"

    if accounts_path.exists():
        data = json.loads(accounts_path.read_text(encoding="utf-8"))
        changed = False
        for item in data:
            value = str(item.get("real_name") or "").strip()
            if value and not is_valid_name(value):
                item["real_name"] = ""
                changed = True
        if changed:
            accounts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        accounts = state.get("accounts") or {}
        changed = False
        for item in accounts.values():
            value = str(item.get("real_name") or "").strip()
            if value and not is_valid_name(value):
                item["real_name"] = ""
                changed = True
        if changed:
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

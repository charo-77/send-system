from __future__ import annotations

import json
from pathlib import Path

STATE_PATH = Path(r"D:\milu_publish_reverse_20260513\runtime\account_manager\browser_workspace_state.json")


def main() -> int:
    if not STATE_PATH.exists():
        print({"changed": 0, "reason": "missing"})
        return 0
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    accounts = payload.get("accounts") or {}
    changed = 0
    for snapshot in accounts.values():
        if not isinstance(snapshot, dict):
            continue
        if snapshot.get("publish_quota"):
            snapshot["publish_quota"] = ""
            changed += 1
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print({"changed": changed, "path": str(STATE_PATH)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

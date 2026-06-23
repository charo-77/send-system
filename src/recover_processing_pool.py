from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

POOL_TODO_DIR = "待发布"
POOL_PROCESSING_DIR = "处理中"
LEDGER_NAME = "A发布记录.jsonl"


def append_ledger(root: Path, row: dict) -> None:
    path = root / LEDGER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Recover stale docx from 处理中/<worker>/ back to 待发布")
    ap.add_argument("root", help="pool root folder")
    ap.add_argument("--worker", default=None, help="recover only one worker")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    todo_dir = root / POOL_TODO_DIR
    processing_root = root / POOL_PROCESSING_DIR
    todo_dir.mkdir(parents=True, exist_ok=True)
    processing_root.mkdir(parents=True, exist_ok=True)

    workers = []
    if args.worker:
        workers = [processing_root / args.worker]
    else:
        workers = [p for p in sorted(processing_root.iterdir()) if p.is_dir()]

    rows = []
    for worker_dir in workers:
        worker = worker_dir.name
        for docx in sorted(worker_dir.glob("*.docx")):
            dest = todo_dir / docx.name
            row = {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "recovered_to_todo",
                "worker": worker,
                "source_path": str(docx),
                "processing_path": str(docx),
                "final_path": str(dest),
                "dry_run": bool(args.dry_run),
                "ok": False,
                "failure_reason": "",
            }
            if dest.exists():
                row["status"] = "recover_failed"
                row["failure_reason"] = "todo destination already exists"
                rows.append(row)
                continue
            if not args.dry_run:
                try:
                    docx.replace(dest)
                    row["ok"] = True
                except Exception as e:
                    row["status"] = "recover_failed"
                    row["failure_reason"] = str(e)
            else:
                row["ok"] = True
            rows.append(row)

    for row in rows:
        append_ledger(root, row)

    print(json.dumps({
        "root": str(root),
        "workers": [p.name for p in workers],
        "count": len(rows),
        "rows": rows,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

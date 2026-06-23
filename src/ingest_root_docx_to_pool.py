from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

POOL_TODO_DIR = "待发布"
POOL_PROCESSING_DIR = "处理中"
SUCCESS_DIR = "A发布成功"
FAILED_DIR = "A发布失败"
LEGACY_FAILED_DIR = "A失败发布"
LEDGER_NAME = "A发布记录.jsonl"

SKIP_DIRS = {
    POOL_TODO_DIR,
    POOL_PROCESSING_DIR,
    SUCCESS_DIR,
    FAILED_DIR,
    LEGACY_FAILED_DIR,
}


def append_ledger(root: Path, row: dict) -> None:
    path = root / LEDGER_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def iter_root_docx(root: Path):
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() != ".docx":
            continue
        yield p


def main() -> int:
    ap = argparse.ArgumentParser(description="Move root-level docx into 待发布/ for pool mode")
    ap.add_argument("root", help="publish root folder")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="optional max files to ingest")
    args = ap.parse_args()

    root = Path(args.root)
    todo_dir = root / POOL_TODO_DIR
    processing_dir = root / POOL_PROCESSING_DIR
    success_dir = root / SUCCESS_DIR
    failed_dir = root / FAILED_DIR

    todo_dir.mkdir(parents=True, exist_ok=True)
    processing_dir.mkdir(parents=True, exist_ok=True)
    success_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    moved_rows = []
    seen = 0
    for src in iter_root_docx(root):
        if args.limit is not None and seen >= args.limit:
            break
        seen += 1
        dest = todo_dir / src.name
        row = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "ingested_to_todo",
            "worker": "",
            "title": src.stem,
            "source_path": str(src),
            "processing_path": "",
            "final_path": str(dest),
            "dry_run": bool(args.dry_run),
            "ok": False,
            "failure_reason": "",
        }
        if dest.exists():
            row["status"] = "ingest_skipped"
            row["failure_reason"] = "todo destination already exists"
            moved_rows.append(row)
            continue
        if not args.dry_run:
            try:
                src.replace(dest)
                row["ok"] = True
            except Exception as e:
                row["status"] = "ingest_failed"
                row["failure_reason"] = str(e)
        else:
            row["ok"] = True
        moved_rows.append(row)

    for row in moved_rows:
        append_ledger(root, row)

    print(json.dumps({
        "root": str(root),
        "count": len(moved_rows),
        "moved": len([x for x in moved_rows if x["status"] == "ingested_to_todo" and x["ok"]]),
        "skipped": len([x for x in moved_rows if x["status"] == "ingest_skipped"]),
        "failed": len([x for x in moved_rows if x["status"] == "ingest_failed"]),
        "rows": moved_rows[:20],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

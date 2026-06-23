from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

SUCCESS_DIR = "A发布成功"
FAILED_DIR = "A发布失败"
PROCESSING_DIR = "处理中"
TODO_DIR = "待发布"
LEDGER_NAME = "A发布记录.jsonl"


def iter_docx(folder: Path):
    if not folder.exists():
        return []
    return sorted([p for p in folder.rglob("*.docx") if p.is_file()])


def row(status: str, p: Path, now: str, **extra):
    payload = {
        "time": now,
        "status": status,
        "worker": extra.get("worker", ""),
        "title": p.stem,
        "docx_path": str(p),
        "source_path": extra.get("source_path", ""),
        "processing_path": extra.get("processing_path", ""),
        "final_path": extra.get("final_path", ""),
        "archive": extra.get("archive", {}),
        "success_url": extra.get("success_url", ""),
        "failure_code": extra.get("failure_code", ""),
        "failure_reason": extra.get("failure_reason", ""),
        "activity_status": extra.get("activity_status", ""),
        "activity_name": extra.get("activity_name", ""),
        "cover_mode": extra.get("cover_mode", ""),
        "attempt_no": extra.get("attempt_no", 1),
        "rebuilt": True,
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild A发布记录.jsonl from pool folders")
    ap.add_argument("root", help="articles root folder")
    args = ap.parse_args()

    root = Path(args.root)
    success_dir = root / SUCCESS_DIR
    failed_dir = root / FAILED_DIR
    processing_root = root / PROCESSING_DIR
    todo_dir = root / TODO_DIR
    ledger_path = root / LEDGER_NAME

    rows = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    for p in iter_docx(todo_dir):
        rows.append(row("todo", p, now, source_path=str(p)))

    if processing_root.exists():
        for worker_dir in sorted([x for x in processing_root.iterdir() if x.is_dir()]):
            for p in iter_docx(worker_dir):
                rows.append(row("processing", p, now, worker=worker_dir.name, processing_path=str(p)))

    for p in iter_docx(success_dir):
        rows.append(row(
            "success", p, now,
            final_path=str(p),
            archive={"ok": True, "bucket": SUCCESS_DIR, "from": "", "to": str(p)},
        ))

    for p in iter_docx(failed_dir):
        rows.append(row(
            "failed", p, now,
            final_path=str(p),
            archive={"ok": True, "bucket": FAILED_DIR, "from": "", "to": str(p)},
        ))

    with ledger_path.open("w", encoding="utf-8", newline="\n") as f:
        for item in rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(json.dumps({
        "rebuilt": str(ledger_path),
        "todo": len([x for x in rows if x["status"] == "todo"]),
        "processing": len([x for x in rows if x["status"] == "processing"]),
        "success": len([x for x in rows if x["status"] == "success"]),
        "failed": len([x for x in rows if x["status"] == "failed"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

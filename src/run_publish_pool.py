from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import os

POOL_STATUS_FILE = '.worker_status.json'
MONITOR_DIR_NAME = '发布监控'
LAST_ACTIVITY_FILE = '.last_activity_name.txt'
CONTROL_FILE_NAME = '.publish_control.json'

from account_manager_config import load_worker_configs_from_any

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


def ensure_pool_dirs(root: Path, workers: list[str]) -> None:
    (root / POOL_TODO_DIR).mkdir(parents=True, exist_ok=True)
    processing_root = root / POOL_PROCESSING_DIR
    processing_root.mkdir(parents=True, exist_ok=True)
    (root / SUCCESS_DIR).mkdir(parents=True, exist_ok=True)
    (root / FAILED_DIR).mkdir(parents=True, exist_ok=True)
    for worker in workers:
        (processing_root / worker).mkdir(parents=True, exist_ok=True)


def resolve_worker_root(base_root: Path, mode: str, worker_cfg, group_overrides: dict[str, str] | None = None) -> Path:
    if mode != 'grouped':
        return base_root
    worker_name = str(getattr(worker_cfg, 'worker_name', '') or '').strip()
    override_group = ''
    if group_overrides:
        override_group = str(group_overrides.get(worker_name) or '').strip()
    group_name = override_group or str(getattr(worker_cfg, 'group_name', '') or '').strip()
    if not group_name:
        raise RuntimeError(f'账号 {worker_cfg.worker_name} 未配置分组，无法使用 grouped 模式')
    return base_root / group_name


def iter_root_docx(root: Path):
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() != ".docx":
            continue
        yield p


def build_claimed_name_set(root: Path) -> set[str]:
    names: set[str] = set()
    for bucket in [root / POOL_TODO_DIR, root / SUCCESS_DIR, root / FAILED_DIR, root / LEGACY_FAILED_DIR]:
        if not bucket.exists():
            continue
        for p in bucket.glob("*.docx"):
            if p.is_file():
                names.add(p.name)
    processing_root = root / POOL_PROCESSING_DIR
    if processing_root.exists():
        for p in processing_root.rglob("*.docx"):
            if p.is_file():
                names.add(p.name)
    return names


def ingest_root_docx_to_todo(root: Path, limit: int | None = None) -> dict:
    todo_dir = root / POOL_TODO_DIR
    todo_dir.mkdir(parents=True, exist_ok=True)
    moved_rows = []
    seen = 0
    claimed_names = build_claimed_name_set(root)
    for src in iter_root_docx(root):
        if limit is not None and seen >= limit:
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
            "ok": False,
            "failure_reason": "",
        }
        if src.name in claimed_names:
            row["status"] = "ingest_skipped"
            row["failure_reason"] = "same-name docx already exists in pool buckets"
            moved_rows.append(row)
            append_ledger(root, row)
            continue
        if dest.exists():
            row["status"] = "ingest_skipped"
            row["failure_reason"] = "todo destination already exists"
            moved_rows.append(row)
            append_ledger(root, row)
            continue
        try:
            src.replace(dest)
            row["ok"] = True
            claimed_names.add(src.name)
        except Exception as e:
            row["status"] = "ingest_failed"
            row["failure_reason"] = str(e)
        moved_rows.append(row)
        append_ledger(root, row)
    return {
        "count": len(moved_rows),
        "moved": len([x for x in moved_rows if x["status"] == "ingested_to_todo" and x["ok"]]),
        "skipped": len([x for x in moved_rows if x["status"] == "ingest_skipped"]),
        "failed": len([x for x in moved_rows if x["status"] == "ingest_failed"]),
        "rows": moved_rows,
    }


def parse_accounts(text: str) -> list[str]:
    items = [x.strip() for x in str(text or "").split(",")]
    return [x for x in items if x]


def count_todo(root: Path) -> int:
    todo = root / POOL_TODO_DIR
    if not todo.exists():
        return 0
    return len([p for p in todo.glob("*.docx") if p.is_file()])


def count_root_docx(root: Path) -> int:
    return len(list(iter_root_docx(root)))


def load_worker_status(root: Path, worker: str) -> dict | None:
    path = root / POOL_PROCESSING_DIR / worker / POOL_STATUS_FILE
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        payload = {"raw": path.read_text(encoding='utf-8', errors='ignore')}
    if isinstance(payload, dict):
        payload["_status_path"] = str(path)
    return payload


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    except Exception:
        return True
    return True


def is_busy_worker_status(status: dict | None) -> bool:
    if not status:
        return False
    state = str((status or {}).get('state') or '').strip().lower()
    pid = (status or {}).get('pid')
    if state in {'finished', 'failed', 'stopped', 'aborted', 'cancelled'}:
        return False
    if pid and not _pid_alive(pid):
        return False
    if not state:
        return bool(pid and _pid_alive(pid))
    return True


def make_monitor_run_dir(root: Path) -> Path:
    base = root / MONITOR_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('run_%Y%m%d_%H%M%S')
    run_dir = base / stamp
    n = 2
    while run_dir.exists():
        run_dir = base / f'{stamp}_{n}'
        n += 1
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_control_state(monitor_dir: Path, mode: str = 'running') -> Path:
    path = monitor_dir / CONTROL_FILE_NAME
    payload = {'mode': mode, 'updated_at': datetime.now().astimezone().isoformat(timespec='seconds')}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def write_last_run(root: Path, monitor_dir: Path, requested_accounts: list[str], per_account_count: int, launch_plan: list[dict]) -> Path:
    path = monitor_dir / '.last_run.json'
    run_id = monitor_dir.name
    payload = {
        'time': datetime.now().astimezone().isoformat(timespec='seconds'),
        'run_id': run_id,
        'root': str(root),
        'monitor_dir': str(monitor_dir),
        'accounts': requested_accounts,
        'per_account_count': per_account_count,
        'launch_plan': launch_plan,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def start_monitor_process(root: Path, monitor_dir: Path) -> None:
    monitor_json = monitor_dir / '发布监控.json'
    bridge_script = str(Path(__file__).with_name('publish_pool_monitor_bridge.py'))
    qt_script = str(Path(__file__).with_name('publish_live_monitor_qt.py'))
    py = sys.executable

    bridge_cmd = [py, bridge_script, '--root', str(root), '--out-dir', str(monitor_dir), '--watch']
    qt_cmd = [py, qt_script, str(monitor_json)]

    subprocess.Popen(bridge_cmd, cwd=str(Path(__file__).resolve().parent.parent), creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    subprocess.Popen(qt_cmd, cwd=str(Path(__file__).resolve().parent.parent), creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))


def load_last_activity_name(root: Path) -> str:
    path = root / MONITOR_DIR_NAME / LAST_ACTIVITY_FILE
    if not path.exists():
        return ''
    try:
        return path.read_text(encoding='utf-8').strip()
    except Exception:
        return ''


def save_last_activity_name(root: Path, activity_name: str) -> Path:
    path = root / MONITOR_DIR_NAME / LAST_ACTIVITY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(activity_name or '').strip(), encoding='utf-8')
    return path


def build_worker_command(args, worker: str, debug_dir: Path, worker_root: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("run_publish_draft.py")),
        "--all",
        "--submit",
        "--articles", str(worker_root),
        "--worker", worker,
        "--debug-dir", str(debug_dir),
        "--max-retries", str(args.max_retries),
        "--retry-delay-seconds", str(args.retry_delay_seconds),
        "--limit", str(args.count),
        "--success-interval-seconds", str(args.success_interval_seconds),
    ]
    if args.account_store:
        cmd += ["--account-store", str(args.account_store)]
    elif args.xlsx:
        cmd += ["--worker-config-xlsx", str(args.xlsx)]
    if args.sheet:
        cmd += ["--worker-config-sheet", args.sheet]
    if args.url:
        cmd += ["--url", args.url]
    if args.headless:
        cmd += ["--headless"]
    if args.keep_profile:
        cmd += ["--keep-profile"]
    if args.keep_open_on_failure:
        cmd += ["--keep-open-on-failure"]
    if args.keep_open_after_success:
        cmd += ["--keep-open-after-success"]
    if args.keep_open_before_submit:
        cmd += ["--keep-open-before-submit"]
    if args.recover_processing:
        cmd += ["--recover-processing"]
    for act in args.activity:
        cmd += ["--activity", act]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser(description="Smart pool runner: auto-create pool, auto-ingest root docx, run per-account workers")
    ap.add_argument("--root", required=True, help="publish root folder")
    ap.add_argument("--accounts", required=True, help="comma-separated account names from CK.xlsx, e.g. 重开2,重开3")
    ap.add_argument("--count", type=int, required=True, help="per-account publish count")
    ap.add_argument("--publish-mode", choices=["direct", "grouped"], default="direct", help="direct=all accounts publish from one root; grouped=each account publishes from <root>/<分组>")
    ap.add_argument("--xlsx", default=r"D:\milu_publish_reverse_20260513\CK.xlsx")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--account-store", default=None, help="local account store json path; when set, prefer it over CK.xlsx")
    ap.add_argument("--group-map", default=None, help="json file path: {worker_name: group_name}; used by grouped mode as override")
    ap.add_argument("--url", default="https://baijiahao.baidu.com/builder/rc/edit?type=news")
    ap.add_argument("--debug-root", default=r"D:\milu_publish_reverse_20260513\debug\worker_pool_live")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--visible", action="store_true")
    ap.add_argument("--keep-profile", action="store_true")
    ap.add_argument("--keep-open-before-submit", action="store_true")
    ap.add_argument("--keep-open-on-failure", action="store_true")
    ap.add_argument("--keep-open-after-success", action="store_true")
    ap.add_argument("--recover-processing", action="store_true")
    ap.add_argument("--max-retries", type=int, default=1)
    ap.add_argument("--retry-delay-seconds", type=int, default=5)
    ap.add_argument("--success-interval-seconds", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=0, help="max concurrent worker publish processes; 0 means start all")
    ap.add_argument("--activity", action="append", default=[])
    ap.add_argument("--activity-name", default=None, help="preferred activity name for this run; if not found, fallback to first visible activity")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-busy-workers", action="store_true", help="allow launching even if worker status file already exists")
    args = ap.parse_args()

    if args.count <= 0:
        raise SystemExit("--count 必须 > 0")
    if args.visible:
        args.headless = False

    root = Path(args.root)
    if args.activity_name is None:
        remembered = load_last_activity_name(root)
        if remembered:
            args.activity = [remembered]
    else:
        desired = str(args.activity_name or '').strip()
        if desired:
            args.activity = [desired]
            save_last_activity_name(root, desired)
        else:
            args.activity = []
    debug_root = Path(args.debug_root)
    debug_root.mkdir(parents=True, exist_ok=True)

    requested_accounts = parse_accounts(args.accounts)
    if not requested_accounts:
        raise SystemExit("--accounts 不能为空")

    all_configs = load_worker_configs_from_any(
        xlsx_path=Path(args.xlsx) if args.xlsx else None,
        sheet_name=args.sheet,
        account_store_path=Path(args.account_store) if args.account_store else None,
    )
    config_by_worker = {str(x.worker_name).strip(): x for x in all_configs}
    missing = [x for x in requested_accounts if x not in config_by_worker]
    if missing:
        raise SystemExit(f"CK.xlsx 中找不到账号: {', '.join(missing)}")

    group_overrides = {}
    if args.group_map:
        group_payload = json.loads(Path(args.group_map).read_text(encoding='utf-8'))
        if isinstance(group_payload, dict):
            group_overrides = {str(k).strip(): str(v or '').strip() for k, v in group_payload.items() if str(k).strip()}

    worker_targets = []
    grouped_missing = []
    for worker in requested_accounts:
        cfg = config_by_worker[worker]
        try:
            worker_root = resolve_worker_root(root, args.publish_mode, cfg, group_overrides)
        except Exception as e:
            grouped_missing.append({"worker": worker, "reason": str(e)})
            continue
        worker_targets.append({"worker": worker, "config": cfg, "root": worker_root})

    if grouped_missing:
        print(json.dumps({
            "root": str(root),
            "blocked": True,
            "reason": "group_mapping_missing",
            "details": grouped_missing,
        }, ensure_ascii=False, indent=2))
        raise SystemExit("存在账号未配置分组，当前不能使用 grouped 模式")

    for item in worker_targets:
        ensure_pool_dirs(item['root'], [item['worker']])

    busy_workers = []
    for item in worker_targets:
        worker = item['worker']
        worker_root = item['root']
        status = load_worker_status(worker_root, worker)
        if status and not is_busy_worker_status(status):
            stale_path = Path(str(status.get('_status_path') or ''))
            try:
                if stale_path.exists():
                    stale_path.unlink()
            except Exception:
                pass
            status = None
        if is_busy_worker_status(status):
            busy_workers.append({"worker": worker, "root": str(worker_root), "status": status})
    if busy_workers and not args.allow_busy_workers:
        print(json.dumps({
            "root": str(root),
            "blocked": True,
            "reason": "busy_workers_detected",
            "busy_workers": busy_workers,
        }, ensure_ascii=False, indent=2))
        raise SystemExit("检测到已有同账号 worker 在运行；如确认要强行并发重开，追加 --allow-busy-workers")

    root_docx_before = count_root_docx(root)
    need_total = len(requested_accounts) * args.count

    ingest_summaries = []
    launch_plan = []
    total_todo_before = 0
    total_todo_after = 0
    total_ingested = 0

    global_ingest_by_root: dict[str, dict] = {}
    for item in worker_targets:
        worker_root = item['root']
        root_key = str(worker_root.resolve())
        if root_key in global_ingest_by_root:
            continue
        todo_before = count_todo(worker_root)
        root_docx_before_this = count_root_docx(worker_root)
        ingest_limit = None
        if root_docx_before_this > 0:
            ingest_limit = max(root_docx_before_this, need_total)

        ingest_summary = {"count": 0, "moved": 0, "skipped": 0, "failed": 0, "rows": []}
        if ingest_limit and ingest_limit > 0:
            if args.dry_run:
                preview = [str((worker_root / POOL_TODO_DIR / p.name)) for p in iter_root_docx(worker_root)]
                ingest_summary = {
                    "count": len(preview),
                    "moved": len(preview),
                    "skipped": 0,
                    "failed": 0,
                    "rows": [{"preview_to": x} for x in preview],
                }
            else:
                ingest_summary = ingest_root_docx_to_todo(worker_root, ingest_limit)
        todo_after = count_todo(worker_root) if not args.dry_run else todo_before + ingest_summary.get('moved', 0)
        global_ingest_by_root[root_key] = {
            'root': str(worker_root),
            'root_docx_before': root_docx_before_this,
            'todo_before': todo_before,
            'todo_after': todo_after,
            'ingest_limit': ingest_limit,
            'ingest_summary': {
                'count': ingest_summary.get('count', 0),
                'moved': ingest_summary.get('moved', 0),
                'skipped': ingest_summary.get('skipped', 0),
                'failed': ingest_summary.get('failed', 0),
            },
        }
        total_todo_before += todo_before
        total_todo_after += todo_after
        total_ingested += ingest_summary.get('moved', 0)

    for item in worker_targets:
        worker = item['worker']
        worker_root = item['root']
        cfg = item['config']
        ingest_meta = global_ingest_by_root[str(worker_root.resolve())]
        ingest_summaries.append({
            'worker': worker,
            'group': getattr(cfg, 'group_name', '') or '',
            'root': str(worker_root),
            'root_docx_before': ingest_meta['root_docx_before'],
            'todo_before': ingest_meta['todo_before'],
            'todo_after': ingest_meta['todo_after'],
            'ingest_limit': ingest_meta['ingest_limit'],
            'ingest_summary': ingest_meta['ingest_summary'],
        })

        cmd = build_worker_command(args, worker, debug_root / worker, worker_root)
        launch_plan.append({
            'worker': worker,
            'group': getattr(cfg, 'group_name', '') or '',
            'root': str(worker_root),
            'count': args.count,
            'debug_dir': str(debug_root / worker),
            'command': cmd,
        })

    article_shortage = total_todo_after < need_total


def _account_fingerprint_map(accounts: list[str], configs: list[WorkerConfig]) -> dict[str, str]:
    by_name = {}
    for cfg in configs:
        name = str(cfg.worker_name or cfg.account_name or '').strip()
        if not name:
            continue
        fp = str(getattr(cfg, 'fingerprint_profile', '') or cfg.fingerprint_id or '').strip()
        if fp:
            by_name[name] = fp
    return {name: by_name.get(name, '') for name in accounts}

    summary = {
        "root": str(root),
        "publish_mode": args.publish_mode,
        "accounts": requested_accounts,
        "per_account_count": args.count,
        "requested_total": need_total,
        "success_interval_seconds": args.success_interval_seconds,
        "concurrency": args.concurrency,
        "activity_name": (args.activity[0] if args.activity else ''),
        "root_docx_before": root_docx_before,
        "todo_before": total_todo_before,
        "todo_after": total_todo_after,
        "article_shortage": article_shortage,
        "shortage_count": max(0, need_total - total_todo_after),
        "ingested_total": total_ingested,
        "fingerprint_map": _account_fingerprint_map(requested_accounts, worker_configs),
        "worker_targets": [
            {"worker": x['worker'], "group": getattr(x['config'], 'group_name', '') or '', "root": str(x['root'])}
            for x in worker_targets
        ],
        "ingest_summaries": ingest_summaries,
        "launch_plan": launch_plan,
        "dry_run": bool(args.dry_run),
    }

    monitor_dir = make_monitor_run_dir(root)
    summary['monitor_dir'] = str(monitor_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    write_last_run(root, monitor_dir, requested_accounts, args.count, launch_plan)
    write_control_state(monitor_dir, 'running')
    if article_shortage:
        shortage_path = monitor_dir / '文章不足提醒.txt'
        shortage_path.write_text(f'计划发布 {need_total} 篇，当前待发布 {total_todo_after} 篇，缺少 {max(0, need_total - total_todo_after)} 篇。\n', encoding='utf-8')
    start_monitor_process(root, monitor_dir)

    limit = max(1, int(args.concurrency or 0)) if int(args.concurrency or 0) > 0 else len(launch_plan)
    pending = list(launch_plan)
    running: list[dict] = []
    started: list[dict] = []
    finished: list[dict] = []

    def _launch_one(item: dict):
        proc = subprocess.Popen(item["command"], cwd=str(Path(__file__).resolve().parent.parent))
        meta = {"worker": item["worker"], "pid": proc.pid, "command": item["command"], "proc": proc}
        running.append(meta)
        started.append({"worker": item["worker"], "pid": proc.pid, "command": item["command"]})

    def _write_queue_state():
        queue_path = monitor_dir / 'launch_queue.json'
        queue_path.write_text(json.dumps({
            'root': str(root),
            'concurrency': limit,
            'started': [{k: v for k, v in x.items() if k != 'proc'} for x in running],
            'pending': [{"worker": x['worker'], "command": x['command']} for x in pending],
            'finished': finished,
            'launch_plan': launch_plan,
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    while pending and len(running) < limit:
        _launch_one(pending.pop(0))
    _write_queue_state()

    while running:
        current_running = list(running)
        running = []
        progressed = False
        for meta in current_running:
            code = meta['proc'].poll()
            if code is None:
                running.append(meta)
                continue
            finished.append({"worker": meta['worker'], "pid": meta['pid'], "returncode": code})
            progressed = True
            while pending and len(running) < limit:
                _launch_one(pending.pop(0))
        _write_queue_state()
        if not progressed:
            time.sleep(2)

    print(json.dumps({
        "started": started,
        "finished": finished,
        "pending": [],
        "monitor": str(monitor_dir / '发布监控.json'),
        "monitor_dir": str(monitor_dir),
        "note": "workers scheduled with concurrency limit",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

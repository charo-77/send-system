from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

POOL_PROCESSING_DIR = '处理中'
LEDGER_NAME = 'A发布记录.jsonl'
STATUS_FILE = '.worker_status.json'
LAST_RUN_FILE = '.last_run.json'


def now_str() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except Exception:
            return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def short_state_from_worker_status(state: str) -> str:
    m = {
        'claimed': '准备启动',
        'processing': '正在发布',
        'finished': '已结束',
    }
    return m.get(state, state or '运行中')


def build_monitor(root: Path, out_dir: Path) -> dict[str, Any]:
    ledger_rows = load_jsonl(root / LEDGER_NAME)
    last_run = load_json(out_dir / LAST_RUN_FILE) or {}
    if not last_run:
        last_run = load_json(root / '发布监控' / LAST_RUN_FILE) or {}
    if not last_run:
        last_run = load_json(root / LAST_RUN_FILE) or {}
    last_run_accounts = [str(x).strip() for x in (last_run.get('accounts') or []) if str(x).strip()]
    per_account_count = int(last_run.get('per_account_count') or 0)
    last_run_time = str(last_run.get('time') or '').strip()
    run_started_at = None
    if last_run_time:
        try:
            run_started_at = datetime.fromisoformat(last_run_time)
        except Exception:
            run_started_at = None

    by_worker: dict[str, dict[str, Any]] = defaultdict(lambda: {
        'processing': 0,
        'success': 0,
        'failed': 0,
        'last_processing': None,
        'last_success': None,
        'last_failed': None,
        'run_success': 0,
        'run_failed': 0,
        'run_processing': 0,
        'run_last_processing': None,
        'run_last_success': None,
        'run_last_failed': None,
    })

    for row in ledger_rows:
        worker = str(row.get('worker') or '').strip()
        if not worker:
            continue
        status = str(row.get('status') or '').strip()
        item = by_worker[worker]
        if status == 'processing':
            item['processing'] += 1
            item['last_processing'] = row
        elif status == 'success':
            item['success'] += 1
            item['last_success'] = row
        elif status == 'failed':
            item['failed'] += 1
            item['last_failed'] = row

        row_time = None
        raw_row_time = str(row.get('time') or '').strip()
        if raw_row_time:
            try:
                row_time = datetime.fromisoformat(raw_row_time)
            except Exception:
                row_time = None

        if worker in last_run_accounts and (run_started_at is None or (row_time is not None and row_time >= run_started_at)):
            if status == 'processing':
                item['run_processing'] += 1
                item['run_last_processing'] = row
            elif status == 'success':
                item['run_success'] += 1
                item['run_last_success'] = row
            elif status == 'failed':
                item['run_failed'] += 1
                item['run_last_failed'] = row

    processing_root = root / POOL_PROCESSING_DIR
    worker_names = set(last_run_accounts or by_worker.keys())
    if processing_root.exists() and not last_run_accounts:
        for d in processing_root.iterdir():
            if d.is_dir():
                worker_names.add(d.name)

    windows: dict[str, Any] = {}
    active_count = 0
    success_total = 0
    failed_total = 0

    for idx, worker in enumerate(sorted(worker_names), start=1):
        state_path = processing_root / worker / STATUS_FILE
        state_obj = load_json(state_path) or {}
        agg = by_worker.get(worker, {})
        success_cnt = int(agg.get('run_success', 0) or 0) if last_run_accounts else int(agg.get('success', 0) or 0)
        failed_cnt = int(agg.get('run_failed', 0) or 0) if last_run_accounts else int(agg.get('failed', 0) or 0)
        success_total += success_cnt
        failed_total += failed_cnt

        if last_run_accounts:
            current = agg.get('run_last_processing') or agg.get('run_last_success') or agg.get('run_last_failed') or {}
        else:
            current = agg.get('last_processing') or agg.get('last_success') or agg.get('last_failed') or {}
        current_state = str(state_obj.get('state') or '')
        run_success = int(agg.get('run_success', 0) or 0)
        run_failed = int(agg.get('run_failed', 0) or 0)
        run_processing = int(agg.get('run_processing', 0) or 0)
        has_run_activity = bool(run_success or run_failed or run_processing)
        if last_run_accounts:
            if state_obj and worker in last_run_accounts and has_run_activity and current_state:
                active_count += 1
            status_text = short_state_from_worker_status(current_state) if (state_obj and has_run_activity and current_state) else ('发布失败' if failed_cnt and not success_cnt else '发布成功' if success_cnt else '等待开始')
        else:
            if state_obj:
                active_count += 1
            status_text = short_state_from_worker_status(current_state) if state_obj else ('发布失败' if failed_cnt and not success_cnt else '发布成功' if success_cnt else '等待开始')

        failure_row = (agg.get('run_last_failed') or {}) if last_run_accounts else (agg.get('last_failed') or {})
        title = str((((state_obj.get('current_title') if has_run_activity else '') if last_run_accounts else state_obj.get('current_title')) or current.get('title') or ''))
        processing_path = str((((state_obj.get('current_docx') if has_run_activity else '') if last_run_accounts else state_obj.get('current_docx')) or current.get('processing_path') or current.get('final_path') or ''))
        folder = str(Path(processing_path).parent) if processing_path else ''
        planned_total = int(state_obj.get('planned_total') or 0)
        if last_run_accounts and worker in last_run_accounts:
            planned_total = per_account_count if per_account_count > 0 else max(planned_total, run_success + run_failed + run_processing, 1)
            published = run_success
        else:
            if planned_total <= 0:
                planned_total = max(success_cnt + failed_cnt + int(agg.get('processing', 0) or 0), 1)
            published = success_cnt

        windows[f'窗口{idx}'] = {
            '账号': worker,
            '状态': status_text,
            '更新时间': now_str(),
            '文章标题': title,
            '发布文件夹': folder,
            '文档路径': processing_path,
            '封面模式': str(current.get('cover_mode') or ''),
            '活动状态': str(current.get('activity_status') or ''),
            '活动名称': str(current.get('activity_name') or ''),
            '总共': planned_total,
            '已发布': published,
            '尝试次数': f"{int(current.get('attempt_no') or 1)}/{int(current.get('attempt_no') or 1)}",
            '失败分类': str(failure_row.get('failure_code') or ''),
            '失败原因': str(failure_row.get('failure_reason') or ''),
        }

    if last_run_accounts:
        run_success_total = sum(int(by_worker.get(w, {}).get('run_success', 0) or 0) for w in last_run_accounts)
        run_failed_total = sum(int(by_worker.get(w, {}).get('run_failed', 0) or 0) for w in last_run_accounts)
        overall = f'运行中 · 活跃{active_count} · 本轮成功{run_success_total} · 本轮失败{run_failed_total}' if active_count else f'已结束 · 本轮成功{run_success_total} · 本轮失败{run_failed_total}'
    else:
        overall = f'运行中 · 活跃{active_count} · 成功{success_total} · 失败{failed_total}' if active_count else f'已结束 · 成功{success_total} · 失败{failed_total}'
    return {
        '项目': '百家号发布池监控',
        '更新时间': now_str(),
        '总体状态': overall,
        '窗口': windows,
    }


def write_monitor(out_dir: Path, data: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / '发布监控.json'
    tmp = out_dir / '发布监控.json.tmp'
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    for _ in range(6):
        try:
            tmp.write_text(payload, encoding='utf-8')
            try:
                tmp.replace(path)
            except PermissionError:
                if path.exists():
                    try:
                        path.unlink()
                    except PermissionError:
                        pass
                tmp.replace(path)
            return path
        except PermissionError:
            time.sleep(0.2)
    tmp.write_text(payload, encoding='utf-8')
    try:
        tmp.replace(path)
    except PermissionError:
        pass
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description='Bridge pool worker status + ledger into 发布监控.json')
    ap.add_argument('--root', required=True, help='publish root folder')
    ap.add_argument('--out-dir', default=None, help='monitor output folder; default <root>/发布监控')
    ap.add_argument('--watch', action='store_true', help='keep refreshing monitor json until manually closed')
    ap.add_argument('--interval-ms', type=int, default=1200)
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir) if args.out_dir else (root / '发布监控')

    def emit_once() -> Path:
        data = build_monitor(root, out_dir)
        out = write_monitor(out_dir, data)
        print(json.dumps({'out': str(out), 'summary': data.get('总体状态', ''), 'windows': len(data.get('窗口', {}))}, ensure_ascii=False))
        return out

    if not args.watch:
        emit_once()
        return 0

    import time
    while True:
        emit_once()
        time.sleep(max(args.interval_ms, 300) / 1000.0)


if __name__ == '__main__':
    raise SystemExit(main())

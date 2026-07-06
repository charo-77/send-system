# -*- coding: utf-8 -*-
"""按账号分组的发布监控（显示账号进度和当前发布文章）"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any
from collections import defaultdict

LEDGER_NAME = 'A发布记录.jsonl'


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件"""
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


def _parse_time(value: Any) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def build_monitor_by_account(
    root: Path,
    target_accounts: set[str] | None = None,
    extra_roots: list[Path] | None = None,
    run_started_at: datetime | None = None,
    per_account_count: int = 0,
) -> dict[str, Any]:
    """按账号分组构建监控数据。extra_roots 用于 grouped 模式下合并多个子目录的 ledger。"""
    ledger_rows = load_jsonl(root / LEDGER_NAME)
    # grouped 模式：合并各子目录的 ledger
    for extra in (extra_roots or []):
        ledger_rows += load_jsonl(extra / LEDGER_NAME)
    
    # 按账号分组
    by_account = defaultdict(lambda: {
        'success': 0,
        'failed': 0,
        'processing': 0,
        'total': 0,
        'processing_titles': [],  # 当前发布中的文章标题
        'failure_reasons': [],    # 失败原因列表
    })
    
    latest_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(ledger_rows):
        worker = str(row.get('worker') or '待分配').strip()
        if target_accounts and worker not in target_accounts:
            continue
        row_time = _parse_time(row.get('time'))
        if run_started_at is not None and (row_time is None or row_time < run_started_at):
            continue
        task_key = str(
            row.get('processing_path')
            or row.get('final_path')
            or row.get('source_path')
            or row.get('title')
            or index
        ).strip()
        latest_rows[(worker, task_key)] = row

    for row in latest_rows.values():
        status = str(row.get('status') or '').strip()
        worker = str(row.get('worker') or '待分配').strip()
        title = str(row.get('title') or '').strip()
        failure_reason = str(row.get('failure_reason') or '').strip()
        
        account = by_account[worker]
        account['total'] += 1
        
        if status == 'success':
            account['success'] += 1
        elif status == 'failed':
            account['failed'] += 1
            # 收集失败原因（最多记录 5 个）
            if len(account['failure_reasons']) < 5 and failure_reason:
                account['failure_reasons'].append(failure_reason)
        elif status == 'processing':
            account['processing'] += 1
            account['processing_titles'].append(title[:60])  # 截断标题
    
    if target_accounts:
        for account_name in target_accounts:
            by_account[account_name]

    # 构建账号列表
    accounts = []
    total_success = 0
    total_failed = 0
    total_processing = 0
    planned_grand_total = 0
    
    for account_name in sorted(by_account.keys()):
        data = by_account[account_name]
        success = data['success']
        failed = data['failed']
        processing = data['processing']
        total = data['total']
        
        planned_total = per_account_count if per_account_count > 0 else total
        if target_accounts:
            planned_total = max(planned_total, total)
        total_success += success
        total_failed += failed
        total_processing += processing
        planned_grand_total += planned_total
        
        accounts.append({
            'name': account_name,
            'success': success,
            'failed': failed,
            'processing': processing,
            'total': planned_total,
            'actual_total': total,
            'processing_titles': data['processing_titles'],
            'failure_reasons': data['failure_reasons'],  # 失败原因列表
            'progress': f"{success}/{planned_total}",
        })
    
    # 总体状态
    grand_total = planned_grand_total if target_accounts else (total_success + total_failed + total_processing)
    active = total_processing > 0
    overall = f"{'运行中' if active else '已结束'} · 成功{total_success} · 失败{total_failed} · 发布中{total_processing}/{grand_total}"
    
    return {
        '项目': '百家号发布池监控（按账号）',
        '更新时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '发布目录': str(root),
        '总体状态': overall,
        '统计': {
            '成功': total_success,
            '失败': total_failed,
            '发布中': total_processing,
            '总计': grand_total,
        },
        '账号': accounts,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser(description='按账号分组构建发布监控')
    ap.add_argument('--root', required=True, help='发布根目录')
    ap.add_argument('--out-dir', default=None, help='输出目录')
    ap.add_argument('--watch', action='store_true', help='持续刷新')
    ap.add_argument('--interval-ms', type=int, default=1000)
    args = ap.parse_args()
    
    root = Path(args.root)
    out_dir = Path(args.out_dir) if args.out_dir else (root / '发布监控')
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取本次任务的账号列表和 extra_roots（从 .last_run.json）
    target_accounts = None
    extra_roots: list[Path] = []
    run_started_at: datetime | None = None
    per_account_count = 0
    last_run_file = out_dir / ".last_run.json"
    if last_run_file.exists():
        try:
            last_run_data = json.loads(last_run_file.read_text(encoding='utf-8-sig'))
            accounts_list = last_run_data.get('accounts', [])
            if accounts_list:
                target_accounts = {str(x).strip() for x in accounts_list if str(x).strip()}
            run_started_at = _parse_time(last_run_data.get('time'))
            per_account_count = int(last_run_data.get('per_account_count') or 0)
            # grouped 模式下的各账号 root 列表
            worker_roots = last_run_data.get('worker_roots', {})
            for r in worker_roots.values():
                p = Path(r)
                if p != root and p.exists():
                    extra_roots.append(p)
        except Exception:
            pass

    def emit_once():
        try:
            data = build_monitor_by_account(
                root,
                target_accounts=target_accounts,
                extra_roots=extra_roots,
                run_started_at=run_started_at,
                per_account_count=per_account_count,
            )
            out_file = out_dir / 'monitor.json'
            out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({
                'file': str(out_file),
                'status': data.get('总体状态', ''),
                'accounts': len(data.get('账号', [])),
            }, ensure_ascii=False), flush=True)
            return out_file
        except Exception as e:
            print(json.dumps({'error': str(e)[:200]}, ensure_ascii=False), flush=True)
            return None
    
    if not args.watch:
        emit_once()
        return 0
    
    import time
    while True:
        try:
            emit_once()
        except Exception:
            pass
        time.sleep(max(args.interval_ms, 500) / 1000.0)


if __name__ == '__main__':
    raise SystemExit(main())

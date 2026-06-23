from __future__ import annotations

from pathlib import Path

from account_store import DEFAULT_ACCOUNT_STORE, load_account_records
from worker_pool_xlsx import WorkerConfig, load_worker_configs


def load_worker_configs_from_any(
    xlsx_path: Path | None = None,
    sheet_name: str | None = None,
    account_store_path: Path | None = None,
) -> list[WorkerConfig]:
    if account_store_path:
        items = load_account_records(Path(account_store_path))
        return [
            WorkerConfig(
                row=item.row,
                account_name=item.account_name,
                worker_name=item.worker_name,
                ck=item.ck,
                proxy_mode=item.proxy_mode,
                proxy_ip=item.proxy_ip,
                proxy_port=item.proxy_port,
                proxy_username=item.proxy_username,
                proxy_password=item.proxy_password,
                group_name=item.group_name,
                fingerprint_id=item.fingerprint_id,
            )
            for item in items
        ]
    if xlsx_path:
        return load_worker_configs(Path(xlsx_path), sheet_name)
    if DEFAULT_ACCOUNT_STORE.exists():
        items = load_account_records(DEFAULT_ACCOUNT_STORE)
        if items:
            return [
                WorkerConfig(
                    row=item.row,
                    account_name=item.account_name,
                    worker_name=item.worker_name,
                    ck=item.ck,
                    proxy_mode=item.proxy_mode,
                    proxy_ip=item.proxy_ip,
                    proxy_port=item.proxy_port,
                    proxy_username=item.proxy_username,
                    proxy_password=item.proxy_password,
                    group_name=item.group_name,
                    fingerprint_id=item.fingerprint_id,
                )
                for item in items
            ]
    return []


def resolve_worker_config(
    worker_name: str,
    xlsx_path: Path | None = None,
    sheet_name: str | None = None,
    account_store_path: Path | None = None,
) -> WorkerConfig | None:
    target = str(worker_name or "").strip()
    for item in load_worker_configs_from_any(xlsx_path, sheet_name, account_store_path):
        if str(item.worker_name or "").strip() == target:
            return item
    return None

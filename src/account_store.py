from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from worker_pool_xlsx import WorkerConfig, load_worker_configs


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ACCOUNT_STORE = REPO_ROOT / "runtime" / "account_manager" / "accounts.json"
DEFAULT_SETTINGS_PATH = REPO_ROOT / "runtime" / "account_manager" / "settings.json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class AccountRecord:
    account_name: str
    worker_name: str
    ck: str
    real_name: str = ""
    group_name: str = ""
    proxy_mode: str = ""
    proxy_ip: str = ""
    proxy_port: str = ""
    proxy_username: str = ""
    proxy_password: str = ""
    fingerprint_id: str = ""
    fingerprint_profile: str = ""
    note: str = ""
    enabled: bool = True
    source: str = "manual"
    row: int = 0
    created_at: str = ""
    updated_at: str = ""
    last_opened_at: str = ""
    online_status: str = "unknown"

    @property
    def display_name(self) -> str:
        return self.real_name or self.account_name or self.worker_name

    @property
    def nickname(self) -> str:
        return self.worker_name or self.account_name or self.real_name

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ck_len"] = len(self.ck or "")
        data.pop("ck", None)
        return data

    def to_worker_config(self) -> WorkerConfig:
        return WorkerConfig(
            row=self.row,
            account_name=self.account_name,
            worker_name=self.worker_name,
            ck=self.ck,
            proxy_mode=self.proxy_mode,
            proxy_ip=self.proxy_ip,
            proxy_port=self.proxy_port,
            proxy_username=self.proxy_username,
            proxy_password=self.proxy_password,
            group_name=self.group_name,
            fingerprint_id=self.fingerprint_id,
            fingerprint_profile=self.fingerprint_profile,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AccountRecord":
        return cls(
            account_name=str(payload.get("account_name") or "").strip(),
            worker_name=str(payload.get("worker_name") or payload.get("account_name") or "").strip(),
            ck=str(payload.get("ck") or "").strip(),
            real_name=str(payload.get("real_name") or payload.get("account_name") or "").strip(),
            group_name=str(payload.get("group_name") or "").strip(),
            proxy_mode=str(payload.get("proxy_mode") or "").strip(),
            proxy_ip=str(payload.get("proxy_ip") or "").strip(),
            proxy_port=str(payload.get("proxy_port") or "").strip(),
            proxy_username=str(payload.get("proxy_username") or "").strip(),
            proxy_password=str(payload.get("proxy_password") or "").strip(),
            fingerprint_id=str(payload.get("fingerprint_id") or "").strip(),
            fingerprint_profile=str(payload.get("fingerprint_profile") or payload.get("fingerprint_id") or "").strip(),
            note=str(payload.get("note") or "").strip(),
            enabled=bool(payload.get("enabled", True)),
            source=str(payload.get("source") or "manual").strip() or "manual",
            row=int(payload.get("row") or 0),
            created_at=str(payload.get("created_at") or "").strip(),
            updated_at=str(payload.get("updated_at") or "").strip(),
            last_opened_at=str(payload.get("last_opened_at") or "").strip(),
            online_status=str(payload.get("online_status") or "unknown").strip() or "unknown",
        )


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_account_records(path: Path | None = None) -> list[AccountRecord]:
    store_path = Path(path) if path else DEFAULT_ACCOUNT_STORE
    if not store_path.exists():
        return []
    raw = store_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not raw:
        return []
    payload = json.loads(raw)
    if not isinstance(payload, list):
        return []
    items = [AccountRecord.from_dict(item) for item in payload if isinstance(item, dict)]
    return sorted(items, key=lambda item: ((item.group_name or "~"), item.display_name.lower(), item.worker_name.lower()))


def save_account_records(items: list[AccountRecord], path: Path | None = None) -> Path:
    store_path = Path(path) if path else DEFAULT_ACCOUNT_STORE
    ensure_parent(store_path)
    payload = [asdict(item) for item in items]
    store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return store_path


def find_account(items: list[AccountRecord], worker_name: str) -> AccountRecord | None:
    needle = str(worker_name or "").strip()
    for item in items:
        if item.worker_name == needle:
            return item
    return None


def upsert_account(items: list[AccountRecord], record: AccountRecord) -> list[AccountRecord]:
    existing = find_account(items, record.worker_name)
    if existing is None:
        items.append(record)
        return items
    existing.account_name = record.account_name
    if record.real_name:
        existing.real_name = record.real_name
    existing.ck = record.ck
    existing.proxy_mode = record.proxy_mode
    existing.proxy_ip = record.proxy_ip
    existing.proxy_port = record.proxy_port
    existing.proxy_username = record.proxy_username
    existing.proxy_password = record.proxy_password
    existing.fingerprint_id = record.fingerprint_id
    existing.row = record.row
    existing.source = record.source or existing.source
    existing.online_status = record.online_status or existing.online_status
    existing.updated_at = record.updated_at or now_iso()
    if record.group_name:
        existing.group_name = record.group_name
    return items


def import_accounts_from_xlsx(xlsx_path: Path, store_path: Path | None = None, sheet_name: str | None = None) -> dict[str, Any]:
    store_path = Path(store_path) if store_path else DEFAULT_ACCOUNT_STORE
    existing = load_account_records(store_path)
    by_worker = {item.worker_name: item for item in existing}
    imported = load_worker_configs(Path(xlsx_path), sheet_name)
    added = 0
    updated = 0
    skipped = 0
    timestamp = now_iso()

    for cfg in imported:
        worker_name = str(cfg.worker_name or cfg.account_name or "").strip()
        ck = str(cfg.ck or "").strip()
        if not worker_name or not ck:
            skipped += 1
            continue
        previous = by_worker.get(worker_name)
        record = AccountRecord(
            account_name=cfg.account_name,
            worker_name=worker_name,
            ck=ck,
            real_name=previous.real_name if previous and previous.real_name else cfg.account_name,
            group_name=previous.group_name if previous and previous.group_name else cfg.group_name,
            proxy_mode=cfg.proxy_mode,
            proxy_ip=cfg.proxy_ip,
            proxy_port=cfg.proxy_port,
            proxy_username=cfg.proxy_username,
            proxy_password=cfg.proxy_password,
            fingerprint_id=cfg.fingerprint_id,
            fingerprint_profile=cfg.fingerprint_id,
            note=previous.note if previous else "",
            enabled=previous.enabled if previous else True,
            source=f"xlsx:{Path(xlsx_path).name}",
            row=cfg.row,
            created_at=previous.created_at if previous and previous.created_at else timestamp,
            updated_at=timestamp,
            last_opened_at=previous.last_opened_at if previous else "",
            online_status=previous.online_status if previous else "unknown",
        )
        if previous is None:
            existing.append(record)
            by_worker[worker_name] = record
            added += 1
        else:
            previous.account_name = record.account_name
            if record.real_name:
                previous.real_name = record.real_name
            previous.ck = record.ck
            previous.proxy_mode = record.proxy_mode
            previous.proxy_ip = record.proxy_ip
            previous.proxy_port = record.proxy_port
            previous.proxy_username = record.proxy_username
            previous.proxy_password = record.proxy_password
            previous.fingerprint_id = record.fingerprint_id
            previous.fingerprint_profile = record.fingerprint_profile
            previous.row = record.row
            previous.source = record.source
            previous.online_status = previous.online_status or "unknown"
            previous.updated_at = timestamp
            if not previous.group_name and record.group_name:
                previous.group_name = record.group_name
            updated += 1

    save_account_records(existing, store_path)
    return {
        "store_path": str(store_path),
        "xlsx_path": str(xlsx_path),
        "sheet_name": sheet_name or "",
        "imported": len(imported),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "total": len(existing),
    }


def load_settings(path: Path | None = None) -> dict[str, Any]:
    settings_path = Path(path) if path else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        return {}
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_settings(payload: dict[str, Any], path: Path | None = None) -> Path:
    settings_path = Path(path) if path else DEFAULT_SETTINGS_PATH
    ensure_parent(settings_path)
    settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings_path

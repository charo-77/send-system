from __future__ import annotations

import json
import re
from pathlib import Path

from account_store import AccountRecord, now_iso, save_account_records


def _is_valid_real_name(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if len(text) < 2 or len(text) > 24:
        return False
    if text in {"99+", "44", "55", "66", "77", "88"}:
        return False
    if text.isdigit():
        return False
    if text.endswith("+") and text[:-1].isdigit():
        return False
    if text.startswith("(") and text.endswith("s)"):
        return False
    if not any("\u4e00" <= ch <= "\u9fff" or ch.isalpha() for ch in text):
        return False
    return True


def _clean_income(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    matches = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not matches:
        return ""
    return matches[0]


def _clean_publish_quota(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", text)
    if not match:
        return ""
    used = int(match.group(1))
    total = int(match.group(2))
    if total <= 0 or total > 15 or used < 0 or used > total:
        return ""
    remain = total - used
    return f"({used}/{remain}/{total})"


def _format_publish_quota(today_published: str, max_publish_number: str, fallback: str) -> str:
    used_text = _clean_income(today_published)
    total_text = _clean_income(max_publish_number)
    if used_text and total_text:
        used = int(float(used_text))
        total = int(float(total_text))
        if 0 <= used <= total <= 15:
            remain = total - used
            return f"({used}/{remain}/{total})"
    return _clean_publish_quota(fallback)


def _clean_org_name(value: str) -> str:
    text = str(value or "").strip()
    return "" if text in {"-", "--", "暂无", "未绑定"} else text


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "runtime" / "account_manager" / "browser_workspace_state.json"


def load_browser_state() -> dict:
    if not STATE_PATH.exists():
        return {"accounts": {}}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("accounts", {})
            return payload
    except Exception:
        pass
    return {"accounts": {}}


def apply_browser_state(accounts: list[AccountRecord]) -> list[dict]:
    state = load_browser_state()
    state_accounts = state.get("accounts") or {}
    rows: list[dict] = []
    for item in accounts:
        snapshot = state_accounts.get(item.worker_name) or {}
        if snapshot.get("online_status"):
            item.online_status = str(snapshot.get("online_status") or item.online_status)
        candidate_name = str(snapshot.get("real_name") or "").strip()
        confidence = str(snapshot.get("real_name_confidence") or "").strip().lower()
        if confidence == "high" and _is_valid_real_name(candidate_name):
            item.real_name = candidate_name
        rows.append(
            {
                "worker_name": item.worker_name,
                "real_name": item.real_name or item.account_name or item.worker_name,
                "group_name": item.group_name,
                "online_status": item.online_status or "unknown",
                "org_name": _clean_org_name(snapshot.get("org_name") or ""),
                "yesterday_income": _clean_income(snapshot.get("yesterday_income") or ""),
                "publish_quota": _format_publish_quota(
                    snapshot.get("today_published_count") or "",
                    snapshot.get("max_publish_number") or "",
                    snapshot.get("publish_quota") or "",
                ),
                "activity_value": _clean_income(snapshot.get("activity_value") or ""),
                "publish_count_total": _clean_income(snapshot.get("publish_count_total") or ""),
                "today_published_count": _clean_income(snapshot.get("today_published_count") or ""),
                "max_publish_number": _clean_income(snapshot.get("max_publish_number") or ""),
                "page_mode": str(snapshot.get("page_mode") or "").strip(),
                "url": str(snapshot.get("url") or "").strip(),
                "checked_at": str(snapshot.get("checked_at") or state.get("last_updated") or "").strip(),
                "real_name_confidence": confidence,
                "real_name_source": str(snapshot.get("real_name_source") or "").strip(),
                "account_status": str(snapshot.get("account_status") or "").strip(),
            }
        )
    for item in accounts:
        item.updated_at = now_iso()
    save_account_records(accounts)
    return rows

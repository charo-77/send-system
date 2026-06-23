from __future__ import annotations

import argparse
import asyncio
import json
import hashlib
import os
import re
import shutil
import uuid
from collections import defaultdict
from datetime import datetime
import os
import time
from pathlib import Path

from docx.opc.exceptions import PackageNotFoundError

from articles import extract_docx_article, extract_docx_images, list_docx
from cookies import load_cookie_file
from browser_publish import publish_draft
from publish_monitor import PublishMonitor
from status_labels import cn_state
from account_manager_config import load_worker_configs_from_any


RETRYABLE_FAILURE_CODES = {
    "network",
    "wrong_entry",
    "doc_import_open",
    "submit_click_failed",
    "submit_no_success_marker",
    "submit_unknown",
}


def _cover_mode_from_image_count(image_count: int) -> str:
    if image_count <= 0:
        return "ai"
    if image_count == 1:
        return "single"
    return "three"


def _batch_result_path(debug_root: Path) -> Path:
    return debug_root / "publish_results.json"


def _batch_report_json_path(debug_root: Path) -> Path:
    return debug_root / "batch_report.json"


def _batch_report_txt_path(debug_root: Path) -> Path:
    return debug_root / "batch_report.txt"


POOL_TODO_DIR = "待发布"
POOL_PROCESSING_DIR = "处理中"
POOL_SUCCESS_DIR = "A发布成功"
POOL_FAILED_DIR = "A发布失败"
LEDGER_NAME = "A发布记录.jsonl"
MAX_PROCESSING_PATH_LEN = 220

CONTROL_FILE_NAME = ".publish_control.json"


def _control_path(root_dir: Path) -> Path:
    return root_dir / "发布监控" / CONTROL_FILE_NAME


def _load_control(root_dir: Path) -> dict:
    path = _control_path(root_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _control_mode(root_dir: Path) -> str:
    return str(_load_control(root_dir).get("mode") or "running").strip().lower()


async def _wait_if_paused(root_dir: Path, monitor: PublishMonitor, slot: int, worker: str) -> bool:
    while True:
        mode = _control_mode(root_dir)
        if mode in {"stop", "stop_after_current", "stopping"}:
            monitor.update_slot(slot, cn_state("FAILED"), 账号=worker, 说明="收到停止发布指令，不再领取新文章", 失败分类="stopped_by_user")
            return False
        if mode not in {"pause", "paused"}:
            return True
        monitor.update_slot(slot, "已暂停", 账号=worker, 说明="暂停发布中，再点继续后恢复领取下一篇")
        await asyncio.sleep(2)


def _pool_todo_dir(root: Path) -> Path:
    return root / POOL_TODO_DIR


def _pool_processing_dir(root: Path, worker: str) -> Path:
    return root / POOL_PROCESSING_DIR / worker


def _pool_success_dir(root: Path) -> Path:
    return root / POOL_SUCCESS_DIR


def _pool_failed_dir(root: Path) -> Path:
    return root / POOL_FAILED_DIR


def _ensure_pool_dirs(root: Path, worker: str) -> None:
    _pool_todo_dir(root).mkdir(parents=True, exist_ok=True)
    _pool_processing_dir(root, worker).mkdir(parents=True, exist_ok=True)
    _pool_success_dir(root).mkdir(parents=True, exist_ok=True)
    _pool_failed_dir(root).mkdir(parents=True, exist_ok=True)


def _list_todo_docx(root: Path) -> list[Path]:
    todo = _pool_todo_dir(root)
    if not todo.exists():
        return []
    return sorted([p for p in todo.rglob("*.docx") if p.is_file()])


def _make_processing_docx_name(src: Path, worker: str) -> str:
    safe_worker = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", worker or "worker").strip("_") or "worker"
    base_title = _clean_article_title(src.stem) or "doc"
    return f"{safe_worker}__{base_title}{src.suffix}"


def _clean_article_title(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(?:\d{6,}|\d{4}[-_]?\d{2}[-_]?\d{2}[-_]?\d{0,6})(?:__|[_\-\s]+)", "", text)
    parts = text.split("__")
    if len(parts) >= 4 and re.fullmatch(r"\d{8}_\d{6}_\d+", parts[0] or ""):
        text = parts[-1]
    elif len(parts) >= 3 and parts[0].isdigit():
        text = parts[-1]
    text = re.sub(r"^[^_\\/]{1,30}__", "", text)
    text = re.sub(r"^\d+[._、\-\s]+", "", text)
    return text.strip(" _-，。；：、") or str(value or "").strip()

def _try_acquire_claim_lock(src: Path, worker: str) -> Path | None:
    # Use an ASCII hash lock name instead of appending to the Chinese/original docx filename.
    # Windows can deny creating sidecar files for names containing curly quotes/special chars.
    digest = hashlib.sha1(str(src).encode("utf-8", errors="ignore")).hexdigest()[:16]
    lock_dir = src.parent / ".claim_locks"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    lock_path = lock_dir / f"{digest}.claim.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"worker={worker}\ntime={datetime.now().astimezone().isoformat(timespec='seconds')}\nsource={src}\n")
        return lock_path
    except (FileExistsError, FileNotFoundError, PermissionError, OSError):
        return None


def _claim_next_docx(root: Path, worker: str) -> tuple[Path | None, dict | None]:
    _ensure_pool_dirs(root, worker)
    todo_files = _list_todo_docx(root)
    processing_dir = _pool_processing_dir(root, worker)
    for src in todo_files:
        lock_path = _try_acquire_claim_lock(src, worker)
        if not lock_path:
            continue
        dest = processing_dir / _make_processing_docx_name(src, worker)
        try:
            if not src.exists():
                return None, {"ok": False, "from": str(src), "to": str(dest), "worker": worker, "error": "source disappeared after claim lock", "original_name": src.name}
            src.replace(dest)
            return dest, {"ok": True, "from": str(src), "to": str(dest), "worker": worker, "original_name": src.name, "claim_lock": str(lock_path)}
        except FileNotFoundError:
            continue
        except Exception as e:
            return None, {"ok": False, "from": str(src), "to": str(dest), "worker": worker, "error": str(e), "original_name": src.name, "claim_lock": str(lock_path)}
        finally:
            try:
                if lock_path.exists():
                    lock_path.unlink()
            except Exception:
                pass
    return None, None


def _make_skip_summary(docx_path: Path, title: str, reason: str) -> dict:
    return {
        "title": title,
        "docx_path": str(docx_path),
        "cover_mode": "",
        "activity_status": "未执行",
        "activity_name": "",
        "published": False,
        "success_url": "",
        "failure_code": "skipped",
        "failure_reason": reason,
        "attempt_no": 0,
        "max_attempts": 0,
        "retryable": False,
        "skipped": True,
        "skip_reason": reason,
    }


def _pick_archive_destination(target_dir: Path, docx_name: str) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    candidate = target_dir / docx_name
    if not candidate.exists():
        return candidate
    stem = Path(docx_name).stem
    suffix = Path(docx_name).suffix
    n = 2
    while True:
        candidate = target_dir / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _archive_processed_docx(pool_root: Path, docx_path: Path, success: bool, fallback_paths: list[str] | None = None) -> dict:
    bucket = POOL_SUCCESS_DIR if success else POOL_FAILED_DIR
    target_dir = _pool_success_dir(pool_root) if success else _pool_failed_dir(pool_root)
    candidate_paths: list[Path] = [docx_path]
    for raw in fallback_paths or []:
        if raw:
            candidate_paths.append(Path(raw))
    checked: list[str] = []
    for candidate in candidate_paths:
        checked.append(str(candidate))
        try:
            if not candidate.exists():
                continue
            dest = _pick_archive_destination(target_dir, candidate.name)
            candidate.replace(dest)
            return {"ok": True, "bucket": bucket, "from": str(candidate), "to": str(dest)}
        except Exception as e:
            return {"ok": False, "bucket": bucket, "from": str(candidate), "error": str(e), "checked": checked}
    return {"ok": False, "bucket": bucket, "from": str(docx_path), "error": "source docx not found for archive", "checked": checked}


def _ledger_path(root_dir: Path) -> Path:
    return root_dir / LEDGER_NAME


def _normalize_worker_name(value: str) -> str:
    text = str(value or "").strip()
    return text or "worker"


def _status_path(root_dir: Path, worker: str) -> Path:
    return _pool_processing_dir(root_dir, worker) / ".worker_status.json"


def _write_worker_status(root_dir: Path, worker: str, payload: dict) -> Path:
    path = _status_path(root_dir, worker)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload or {})
    data.setdefault("pid", os.getpid())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _clear_worker_status(root_dir: Path, worker: str) -> None:
    path = _status_path(root_dir, worker)
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _recover_processing_files(root: Path, worker: str) -> list[dict]:
    processing_dir = _pool_processing_dir(root, worker)
    todo_dir = _pool_todo_dir(root)
    todo_dir.mkdir(parents=True, exist_ok=True)
    if not processing_dir.exists():
        return []
    recovered: list[dict] = []

    def _recover_original_name(name: str) -> str:
        current = name
        while True:
            parts = current.split("__", 2)
            if len(parts) == 3 and parts[0].isdigit() and len(parts[0]) >= 14:
                current = parts[2]
                continue
            if current.startswith(worker + "__"):
                current = current[len(worker) + 2:]
                continue
            return current

    for p in sorted(processing_dir.glob("*.docx")):
        recovered_name = _recover_original_name(p.name)
        dest = todo_dir / recovered_name
        row = {
            "worker": worker,
            "from": str(p),
            "to": str(dest),
            "recovered_name": recovered_name,
            "ok": False,
            "reason": "",
        }
        if dest.exists():
            row["reason"] = "todo destination already exists; skip recover"
            recovered.append(row)
            continue
        try:
            p.replace(dest)
            row["ok"] = True
        except Exception as e:
            row["reason"] = str(e)
        recovered.append(row)
    return recovered


def _safe_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("\ufffd", "").strip()


def _should_fail_long_processing_path(path: Path) -> bool:
    try:
        return len(str(path)) > MAX_PROCESSING_PATH_LEN
    except Exception:
        return False


def _build_direct_failure_result(docx_path: Path, article_title: str, attempt_no: int, failure_code: str, failure_reason: str) -> dict:
    structured_result = {
        "title": article_title,
        "docx_path": str(docx_path),
        "cover_mode": "",
        "activity_status": "",
        "activity_name": "",
        "published": False,
        "success_url": "",
        "failure_code": failure_code,
        "failure_reason": failure_reason,
        "attempt_no": attempt_no,
        "max_attempts": 1,
        "retryable": False,
    }
    return {
        "published": False,
        "structured_result": structured_result,
        "monitor_summary": structured_result,
        "page_state": {"url": "", "body_snippet": ""},
    }


def _build_path_too_long_result(docx_path: Path, article_title: str, attempt_no: int) -> dict:
    return _build_direct_failure_result(
        docx_path=docx_path,
        article_title=article_title,
        attempt_no=attempt_no,
        failure_code="path_too_long",
        failure_reason=f"processing path too long: {len(str(docx_path))} > {MAX_PROCESSING_PATH_LEN}",
    )


def _append_ledger_entry(root_dir: Path, entry: dict) -> None:
    def sanitize(obj):
        if isinstance(obj, dict):
            return {k: sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(x) for x in obj]
        if isinstance(obj, tuple):
            return [sanitize(x) for x in obj]
        if isinstance(obj, str):
            return _safe_text(obj)
        return obj

    path = _ledger_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(sanitize(entry), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _classify_failure(result: dict) -> tuple[str, str]:
    page_state = result.get("page_state") or {}
    page_text = str(page_state.get("body_snippet") or "")
    current_url = str(page_state.get("url") or "")
    import_doc = result.get("import_doc") or {}
    import_verify = result.get("import_verify") or {}
    fill = result.get("fill") or {}
    cover = result.get("cover") or {}
    activity = result.get("activity") or {}
    submit = result.get("submit") or {}

    if result.get("published"):
        return "", ""
    platform_blockers = list((submit.get("platform_blockers") or page_state.get("platform_blockers") or []))
    if platform_blockers:
        return "platform_blocker", str(platform_blockers[0])[:300]
    if bool(submit.get("captcha_required") or page_state.get("has_captcha")):
        return "captcha", "???????????????"
    page_text_low = page_text.lower()
    page_url_low = str(result.get("page_url") or "").lower()
    if (
        "百度安全验证" in page_text
        or "拖动左侧滑块使图片为正" in page_text
        or "captcha" in page_text_low
        or ("verify" in page_text_low and "security" in page_text_low)
        or "wappass.baidu.com" in page_url_low
        or ("verify" in page_url_low and "baidu" in page_url_low)
        or "captcha" in page_url_low
        or bool((result.get("initial_state") or {}).get("has_captcha"))
    ):
        return "captcha", "百度验证码/安全验证未完成"
    news_guard_ok = ((result.get("initial_state") or {}).get("news_guard", {}).get("ok"))
    has_later_progress = bool(
        (result.get("fill") or {}).get("title_filled")
        or (result.get("fill") or {}).get("body_filled")
        or (result.get("import_verify") or {}).get("ok")
        or (result.get("submit") or {}).get("attempted")
    )
    if news_guard_ok is False and not has_later_progress:
        return "wrong_entry", "未稳定进入 type=news 图文编辑页"
    fill_ready = bool(fill.get("title_filled") and fill.get("body_filled"))
    import_ready = bool(import_verify.get("ok"))
    content_ready = fill_ready or import_ready
    manual_fill_mode = any(str(x.get("reason") or "") == "manual_fill_mode" for x in (import_doc.get("steps") or []))
    if not manual_fill_mode and import_doc.get("attempted") and not import_doc.get("uploaded"):
        return "doc_import_open", "导入文档入口或上传控件未成功触发"
    if not content_ready and not manual_fill_mode and import_doc.get("attempted") and import_doc.get("uploaded") and not import_verify.get("ok"):
        return "doc_import_materialize", "文档已上传但正文/标题未真正落地到编辑器"
    if manual_fill_mode and not content_ready:
        return "fill_failed", "标题或正文未成功写入编辑器"
    if cover.get("skipped"):
        return "cover_skipped", str(cover.get("reason") or "封面流程被跳过")
    if cover.get("attempted") and not cover.get("confirmed") and not cover.get("uploaded"):
        return "cover_failed", "封面流程未确认完成"
    if activity.get("requested") and activity.get("missing"):
        return "activity_mismatch", "指定活动未匹配成功"
    if submit.get("attempted") and not submit.get("clicked"):
        return "submit_click_failed", "发布按钮未成功点击"
    if submit.get("attempted") and submit.get("clicked") and not submit.get("published"):
        if "clue" in current_url:
            return "submit_unknown", "已提交但成功标记识别不完整"
        return "submit_no_success_marker", "已执行发布，但未识别到成功页标记"
    if any(str(x.get("status")) in {"502", "503", "504"} for x in (result.get("network_events_tail") or [])):
        return "network", "疑似网络抖动或服务端临时异常"
    return "unknown", "未命中已知失败分类"


def _is_login_redirect_failure(structured: dict, final_summary: dict | None = None) -> bool:
    failure_code = str((structured or {}).get("failure_code") or "").strip()
    if failure_code != "wrong_entry":
        return False
    success_url = str((structured or {}).get("success_url") or "")
    page_state = ((final_summary or {}).get("page_state") or {})
    page_url = str(page_state.get("url") or (final_summary or {}).get("page_url") or "")
    body = str(page_state.get("body_snippet") or "")
    joined = f"{success_url}\n{page_url}\n{body}"
    return ("builder/theme/bjh/login" in joined) or ("账号登录" in joined) or ("登录" in body and "手机号" in body)


def _mark_account_offline(worker: str, account_store_path: str | None, reason: str, title: str = "") -> None:
    try:
        store_path = Path(account_store_path) if account_store_path else DEFAULT_ACCOUNT_STORE
        items = load_account_records(store_path)
        target = str(worker or "").strip()
        now = now_iso()
        changed = False
        for item in items:
            if str(item.worker_name or "").strip() != target:
                continue
            item.online_status = "offline"
            item.updated_at = now
            extra = f"掉线: {reason}"
            if title:
                extra += f" | {title}"
            item.note = extra if not item.note else f"{item.note} | {extra}"
            changed = True
            break
        if changed:
            save_account_records(items, store_path)
    except Exception:
        pass


def _activity_summary(payload: dict) -> tuple[str, str]:
    selected = payload.get("selected") or []
    if selected:
        names = [str(x.get("name") or x.get("matchedText") or x.get("targetText") or "") for x in selected]
        names = [x for x in names if x]
        return "已添加", ' / '.join(names) if names else "AUTO_FIRST_VISIBLE"
    requested = [str(x) for x in (payload.get("requested") or []) if x]
    missing = [str(x) for x in (payload.get("missing") or []) if x]
    available = [str(x) for x in (payload.get("available") or []) if x]
    if requested and missing and len(missing) == len(requested):
        return "未匹配", ' / '.join(missing)
    if requested:
        return "未添加", ' / '.join(requested)
    if available:
        return "未添加", available[0]
    return "未添加", ""


def _should_retry(failure_code: str, attempt_no: int, max_retries: int) -> bool:
    return attempt_no <= max_retries and failure_code in RETRYABLE_FAILURE_CODES


def _summarize_batch_results(results: list[dict], total_count: int, max_retries: int, mode: str) -> dict:
    structured = [item.get("structured_result") or item.get("monitor_summary") or {} for item in results]
    failure_groups: dict[str, list[dict]] = defaultdict(list)
    retry_succeeded: list[dict] = []
    first_try_success = 0

    for item in structured:
        if item.get("published"):
            if int(item.get("attempt_no") or 1) > 1:
                retry_succeeded.append({
                    "title": item.get("title", ""),
                    "docx_path": item.get("docx_path", ""),
                    "attempt_no": item.get("attempt_no", 1),
                    "success_url": item.get("success_url", ""),
                })
            else:
                first_try_success += 1
            continue

        code = str(item.get("failure_code") or "unknown")
        failure_groups[code].append({
            "title": item.get("title", ""),
            "docx_path": item.get("docx_path", ""),
            "attempt_no": item.get("attempt_no", 1),
            "failure_reason": item.get("failure_reason", ""),
            "cover_mode": item.get("cover_mode", ""),
            "activity_name": item.get("activity_name", ""),
        })

    failure_summary = {
        code: {
            "count": len(items),
            "items": items,
        }
        for code, items in sorted(failure_groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    }

    return {
        "mode": mode,
        "total": total_count,
        "completed": len(structured),
        "published": sum(1 for x in structured if x.get("published")),
        "failed": sum(1 for x in structured if not x.get("published")),
        "first_try_success": first_try_success,
        "retry_success": len(retry_succeeded),
        "max_retries": max_retries,
        "retryable_failure_codes": sorted(RETRYABLE_FAILURE_CODES),
        "failure_summary": failure_summary,
        "retry_succeeded_items": retry_succeeded,
        "results": structured,
    }


def _render_batch_report_text(report: dict) -> str:
    lines = []
    lines.append("批量发布汇总")
    lines.append("=" * 24)
    lines.append(f"模式：{report.get('mode', '')}")
    lines.append(f"总数：{report.get('total', 0)}")
    lines.append(f"已完成：{report.get('completed', 0)}")
    lines.append(f"发布成功：{report.get('published', 0)}")
    lines.append(f"发布失败：{report.get('failed', 0)}")
    lines.append(f"首次成功：{report.get('first_try_success', 0)}")
    lines.append(f"重试后成功：{report.get('retry_success', 0)}")
    lines.append(f"最大重试：{report.get('max_retries', 0)}")
    lines.append("")

    retry_succeeded = report.get("retry_succeeded_items") or []
    if retry_succeeded:
        lines.append("重试后成功")
        lines.append("-" * 24)
        for item in retry_succeeded:
            lines.append(f"- 第{item.get('attempt_no', 1)}次成功 | {item.get('title', '')}")
        lines.append("")

    failure_summary = report.get("failure_summary") or {}
    if failure_summary:
        lines.append("失败分组")
        lines.append("-" * 24)
        for code, info in failure_summary.items():
            lines.append(f"[{code}] {info.get('count', 0)}篇")
            for item in info.get("items") or []:
                lines.append(
                    f"  - 第{item.get('attempt_no', 1)}次 | {item.get('title', '')} | {item.get('failure_reason', '')}"
                )
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def _write_running_results(debug_root: Path, results: list[dict], batch_summary: dict | None = None) -> None:
    payload = batch_summary or [item.get("structured_result") or item.get("monitor_summary") for item in results]
    _batch_result_path(debug_root).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_batch_report(debug_root: Path, report: dict) -> None:
    _batch_report_json_path(debug_root).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _batch_report_txt_path(debug_root).write_text(_render_batch_report_text(report), encoding="utf-8")


async def publish_one(
    docx_path: Path,
    slot: int,
    args,
    monitor: PublishMonitor,
    profile_dir: Path,
    debug_dir: Path,
    cookies,
    total_count: int,
    published_so_far: int,
    attempt_no: int = 1,
    max_retries: int = 0,
) -> tuple[dict, bool]:
    article = extract_docx_article(docx_path)
    docx_images = extract_docx_images(docx_path, debug_dir / "covers" / f"slot_{slot:02d}")
    cover_path = docx_images[0] if docx_images else None
    cover_mode = _cover_mode_from_image_count(len(docx_images))
    docx_path_str = str(docx_path)
    folder_str = str(docx_path.parent)

    async def status_callback(state: str, payload: dict) -> None:
        monitor_payload = {
            "账号": "百家号图文",
            "文章标题": article.title,
            "文档路径": docx_path_str,
            "发布文件夹": folder_str,
            "封面模式": cover_mode,
            "总共": total_count,
            "已发布": published_so_far + (1 if state == "SUCCESS" else 0),
            "状态码": state,
            "尝试次数": f"{attempt_no}/{max_retries + 1}",
        }
        if state == "ACTIVITY_SELECTING":
            monitor_payload["活动模式"] = str(payload.get("activity") or "AUTO_FIRST_VISIBLE")
        if state == "ACTIVITY_DONE":
            monitor_payload["活动已选择数量"] = payload.get("selected_count", 0)
            monitor_payload["活动缺失数量"] = payload.get("missing_count", 0)
        if state == "SUCCESS":
            monitor_payload["成功标记"] = payload.get("success_markers", "")
            monitor_payload["成功页"] = payload.get("page_url", "")
        if state == "FAILED":
            monitor_payload["失败原因"] = payload.get("reason", "")
            monitor_payload["当前页"] = payload.get("page_url", "")
        if state in {"WAIT_MANUAL_CAPTCHA", "READY_TO_SUBMIT", "SUBMITTING"} and payload.get("message"):
            monitor_payload["说明"] = payload.get("message")
        if state == "BROWSER_STATE":
            monitor_payload["?????"] = payload.get("browser_title", "")
            monitor_payload["???"] = payload.get("page_url", "")
            monitor_payload["??"] = payload.get("word_count", "")
            monitor_payload["????"] = payload.get("body_snippet", "")
            if payload.get("platform_blockers"):
                monitor_payload["????"] = str(payload.get("platform_blockers"))[:500]
            if payload.get("dialogs"):
                monitor_payload["????"] = str(payload.get("dialogs"))[:500]
            if payload.get("has_captcha"):
                monitor_payload["??????"] = "?"
        if state == "COVER_DONE":
            monitor_payload["?????"] = payload.get("cover_confirmed", "")
            if payload.get("cover_steps"):
                monitor_payload["????"] = str(payload.get("cover_steps"))[:800]
        if state == "WAIT_MANUAL_CAPTCHA":
            monitor_payload["??????"] = "?"
            monitor_payload["??"] = payload.get("message") or "??????????????"
        monitor.update_slot(slot, cn_state(state), **monitor_payload)

    monitor.update_slot(
        slot,
        cn_state("INIT"),
        账号="百家号图文",
        文章标题=article.title,
        文档路径=docx_path_str,
        发布文件夹=folder_str,
        封面模式=cover_mode,
        活动模式=' / '.join(args.activity or ['AUTO_FIRST_VISIBLE']),
        总共=total_count,
        已发布=published_so_far,
        尝试次数=f"{attempt_no}/{max_retries + 1}",
    )

    result = await publish_draft(
        article=article,
        cookies=cookies,
        user_data_dir=profile_dir,
        url=args.url,
        headless=args.headless,
        submit=args.submit,
        debug_dir=debug_dir,
        cover_path=cover_path,
        docx_path=docx_path,
        docx_image_count=len(docx_images),
        activity_names=args.activity,
        keep_open_before_submit=args.keep_open_before_submit,
        keep_open_on_failure=args.keep_open_on_failure,
        keep_open_after_success=args.keep_open_after_success,
        status_callback=status_callback,
    )

    activity_status, activity_name = _activity_summary(result.get("activity") or {})
    success_url = ((result.get("page_state") or {}).get("url") or "")
    failure_code, failure_reason = _classify_failure(result)
    structured_result = {
        "title": article.title,
        "docx_path": docx_path_str,
        "cover_mode": cover_mode,
        "activity_status": activity_status,
        "activity_name": activity_name,
        "published": bool(result.get("published")),
        "success_url": success_url,
        "failure_code": failure_code,
        "failure_reason": failure_reason,
        "attempt_no": attempt_no,
        "max_attempts": max_retries + 1,
        "retryable": failure_code in RETRYABLE_FAILURE_CODES,
    }
    final_summary = {
        **result,
        "profile_dir": str(profile_dir),
        "structured_result": structured_result,
        "monitor_summary": structured_result,
    }

    monitor.update_slot(
        slot,
        cn_state("SUCCESS") if result.get("published") else cn_state("FAILED"),
        账号="百家号图文",
        文章标题=article.title,
        文档路径=docx_path_str,
        发布文件夹=folder_str,
        封面模式=cover_mode,
        活动状态=activity_status,
        活动名称=activity_name,
        总共=total_count,
        已发布=published_so_far + (1 if result.get("published") else 0),
        成功页=success_url,
        失败分类=failure_code,
        失败原因=failure_reason,
        尝试次数=f"{attempt_no}/{max_retries + 1}",
    )
    return final_summary, bool(result.get("published"))


async def main() -> int:
    ap = argparse.ArgumentParser(description="Open browser, inject CK, fill one or many docx articles. Submit is opt-in.")
    ap.add_argument("--articles", default=r"C:\Users\Administrator\Desktop\mingming\国际")
    ap.add_argument("--cookie-file", default=r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513\ck.txt")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--all", action="store_true", help="Publish all docx files under --articles in sequence")
    ap.add_argument("--limit", type=int, default=None, help="When used with --all, limit how many files to publish")
    ap.add_argument("--url", default=None)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--keep-profile", action="store_true", help="keep auto-created temp profile directory")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--submit", action="store_true", help="Actually click submit/save button. Default: do not submit.")
    ap.add_argument("--debug-dir", default=r"C:\Users\Administrator\.openclaw\workspace\milu_publish_reverse_20260513\debug")
    ap.add_argument("--activity", action="append", default=[], help="Activity name to select before publish; repeatable")
    ap.add_argument("--keep-open-before-submit", action="store_true", help="Keep browser open on the pre-submit publish page for manual inspection")
    ap.add_argument("--keep-open-on-failure", action="store_true", help="Keep browser open when publish/validation fails for live debugging")
    ap.add_argument("--keep-open-after-success", action="store_true", help="Keep browser open even after successful publish for live verification")
    ap.add_argument("--monitor-slot", type=int, default=1, help="Monitor slot number for single publish mode; batch mode auto-increments from this slot")
    ap.add_argument("--max-retries", type=int, default=0, help="Retry current doc on retryable failure codes in batch/single entry layer")
    ap.add_argument("--retry-delay-seconds", type=int, default=5, help="Delay between retry attempts")
    ap.add_argument("--worker", required=True, help="worker/account name, e.g. 账号A")
    ap.add_argument("--recover-processing", action="store_true", help="before running, move stale docx from 处理中/<worker>/ back to 待发布")
    ap.add_argument("--worker-config-xlsx", default=None, help="optional CK.xlsx path; when set, use the row whose 账号 matches --worker")
    ap.add_argument("--worker-config-sheet", default=None, help="optional worker config sheet name")
    ap.add_argument("--account-store", default=None, help="optional local account store json path")
    ap.add_argument("--success-interval-seconds", type=int, default=0, help="wait N seconds after each successful publish before next docx")
    args = ap.parse_args()

    debug_root = Path(args.debug_dir)
    debug_root.mkdir(parents=True, exist_ok=True)
    articles_root = Path(args.articles)
    worker = _normalize_worker_name(args.worker)
    _ensure_pool_dirs(articles_root, worker)
    monitor = PublishMonitor(debug_root)

    worker_config = None
    if args.worker_config_xlsx or args.account_store:
        items = load_worker_configs_from_any(
            xlsx_path=Path(args.worker_config_xlsx) if args.worker_config_xlsx else None,
            sheet_name=args.worker_config_sheet,
            account_store_path=Path(args.account_store) if args.account_store else None,
        )
        matched = [x for x in items if _normalize_worker_name(x.worker_name) == worker]
        if not matched:
            source_name = "账号库" if args.account_store else "CK.xlsx"
            raise SystemExit(f"在{source_name}中找不到账号/worker: {worker}")
        worker_config = matched[0]
        ck_temp = debug_root / f"{worker}_ck.txt"
        ck_temp.write_text(worker_config.ck, encoding="utf-8")
        cookies = load_cookie_file(ck_temp)
    else:
        cookies = load_cookie_file(Path(args.cookie_file))

    if args.recover_processing:
        recovered = _recover_processing_files(articles_root, worker)
        for item in recovered:
            _append_ledger_entry(articles_root, {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "recovered_to_todo" if item.get("ok") else "recover_failed",
                "worker": worker,
                "source_path": item.get("from", ""),
                "processing_path": item.get("from", ""),
                "final_path": item.get("to", ""),
                "failure_reason": item.get("reason", ""),
            })

    results: list[dict] = []
    published_count = 0
    planned = args.limit if args.all and args.limit else (1 if not args.all else None)
    todo_now = _list_todo_docx(articles_root)
    total_count = planned or len(todo_now)

    claim_plan_total = int(planned or len(todo_now) or 0)
    if claim_plan_total <= 0:
        monitor.update_slot(args.monitor_slot, "文章不足", 账号=worker, 总共=0, 已发布=0, 说明="待发布目录中没有可抢占的 docx")
        _write_worker_status(articles_root, worker, {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "worker": worker,
            "state": "article_insufficient",
            "planned_total": 0,
            "debug_root": str(debug_root),
            "worker_config": (worker_config.to_public_dict() if worker_config else None),
        })
        return 0

    _write_worker_status(articles_root, worker, {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "worker": worker,
        "state": "waiting_claim",
        "planned_total": claim_plan_total,
        "debug_root": str(debug_root),
        "worker_config": (worker_config.to_public_dict() if worker_config else None),
    })

    idx = 0
    while idx < claim_plan_total:
        slot = args.monitor_slot
        if not await _wait_if_paused(articles_root, monitor, slot, worker):
            break
        if args.all:
            claimed, claim_info = _claim_next_docx(articles_root, worker)
            if not claimed:
                monitor.update_slot(slot, "文章不足", 账号=worker, 总共=claim_plan_total, 已发布=published_count, 说明="待发布池已空，不再新开窗口")
                _write_worker_status(articles_root, worker, {
                    "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "worker": worker,
                    "state": "article_insufficient",
                    "published": published_count,
                    "planned_total": claim_plan_total,
                    "debug_root": str(debug_root),
                    "worker_config": (worker_config.to_public_dict() if worker_config else None),
                })
                break
            docx_path, claim_info = claimed, claim_info or {}
        else:
            all_todo = _list_todo_docx(articles_root)
            if not all_todo:
                raise SystemExit("待发布目录中没有 docx")
            if args.index < 0 or args.index >= len(all_todo):
                raise SystemExit(f"index out of range: {args.index}; total={len(all_todo)}")
            chosen = all_todo[args.index]
            desired = _pool_processing_dir(articles_root, worker) / _make_processing_docx_name(chosen, worker)
            if desired.exists():
                raise SystemExit(f"抢单失败: processing destination already exists: {desired}")
            try:
                desired.parent.mkdir(parents=True, exist_ok=True)
                chosen.replace(desired)
                docx_path, claim_info = desired, {"ok": True, "from": str(chosen), "to": str(desired), "worker": worker, "indexed_claim": True, "original_name": chosen.name}
            except FileNotFoundError:
                raise SystemExit("抢单失败: 目标文件已被其他 worker 抢走")
            except Exception as e:
                raise SystemExit(f"抢单失败: {e}")
        idx += 1
        slot = args.monitor_slot
        final_summary = None
        ok = False
        original_name = str((claim_info or {}).get("original_name") or "").strip()
        article_title = _clean_article_title(Path(original_name).stem if original_name else docx_path.stem)

        fallback_paths = [str((claim_info or {}).get("from") or ""), str((claim_info or {}).get("to") or "")]

        if _should_fail_long_processing_path(docx_path):
            final_summary = _build_path_too_long_result(docx_path, article_title, attempt_no=1)
            archive_info = _archive_processed_docx(articles_root, docx_path, success=False, fallback_paths=fallback_paths)
            final_summary["archive"] = archive_info
            results.append(final_summary)
            structured = (final_summary or {}).get("structured_result") or {}
            _append_ledger_entry(articles_root, {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "failed",
                "worker": worker,
                "title": structured.get("title", article_title),
                "source_path": str((claim_info or {}).get("from") or ""),
                "processing_path": str(docx_path),
                "final_path": str((archive_info or {}).get("to") or ""),
                "archive": archive_info,
                "success_url": "",
                "failure_code": structured.get("failure_code", "path_too_long"),
                "failure_reason": structured.get("failure_reason", ""),
                "activity_status": "",
                "activity_name": "",
                "cover_mode": "",
                "attempt_no": 1,
                "claim": claim_info or {},
                "worker_config": (worker_config.to_public_dict() if worker_config else None),
            })
            monitor.update_slot(
                slot,
                cn_state("FAILED"),
                账号="百家号图文",
                文章标题=article_title,
                文档路径=str(docx_path),
                发布文件夹=str(docx_path.parent),
                封面模式="",
                活动状态="",
                活动名称="",
                总共=claim_plan_total,
                已发布=published_count,
                失败分类="path_too_long",
                失败原因=structured.get("failure_reason", ""),
                尝试次数=f"1/{args.max_retries + 1}",
            )
            _write_running_results(debug_root, results)
            report = _summarize_batch_results(results, total_count=claim_plan_total, max_retries=args.max_retries, mode="batch" if args.all else "single")
            _write_batch_report(debug_root, report)
            continue

        if not docx_path.exists():
            final_summary = _build_direct_failure_result(
                docx_path=docx_path,
                article_title=article_title,
                attempt_no=1,
                failure_code="claimed_docx_missing",
                failure_reason="claimed docx missing before read; likely moved, deleted, or conflicted after claim",
            )
            archive_info = _archive_processed_docx(articles_root, docx_path, success=False, fallback_paths=fallback_paths)
            final_summary["archive"] = archive_info
            results.append(final_summary)
            structured = (final_summary or {}).get("structured_result") or {}
            _append_ledger_entry(articles_root, {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "failed",
                "worker": worker,
                "title": structured.get("title", article_title),
                "source_path": str((claim_info or {}).get("from") or ""),
                "processing_path": str(docx_path),
                "final_path": str((archive_info or {}).get("to") or ""),
                "archive": archive_info,
                "success_url": "",
                "failure_code": structured.get("failure_code", "claimed_docx_missing"),
                "failure_reason": structured.get("failure_reason", ""),
                "activity_status": "",
                "activity_name": "",
                "cover_mode": "",
                "attempt_no": 1,
                "claim": claim_info or {},
                "worker_config": (worker_config.to_public_dict() if worker_config else None),
            })
            monitor.update_slot(
                slot,
                cn_state("FAILED"),
                账号="百家号图文",
                文章标题=article_title,
                文档路径=str(docx_path),
                发布文件夹=str(docx_path.parent),
                封面模式="",
                活动状态="",
                活动名称="",
                总共=claim_plan_total,
                已发布=published_count,
                失败分类="claimed_docx_missing",
                失败原因=structured.get("failure_reason", ""),
                尝试次数=f"1/{args.max_retries + 1}",
            )
            _write_running_results(debug_root, results)
            report = _summarize_batch_results(results, total_count=claim_plan_total, max_retries=args.max_retries, mode="batch" if args.all else "single")
            _write_batch_report(debug_root, report)
            continue

        try:
            article = extract_docx_article(docx_path)
        except PackageNotFoundError as e:
            final_summary = _build_direct_failure_result(
                docx_path=docx_path,
                article_title=article_title,
                attempt_no=1,
                failure_code="docx_open_failed",
                failure_reason=f"docx package open failed: {e}",
            )
            archive_info = _archive_processed_docx(articles_root, docx_path, success=False, fallback_paths=fallback_paths)
            final_summary["archive"] = archive_info
            results.append(final_summary)
            structured = (final_summary or {}).get("structured_result") or {}
            _append_ledger_entry(articles_root, {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "failed",
                "worker": worker,
                "title": structured.get("title", article_title),
                "source_path": str((claim_info or {}).get("from") or ""),
                "processing_path": str(docx_path),
                "final_path": str((archive_info or {}).get("to") or ""),
                "archive": archive_info,
                "success_url": "",
                "failure_code": structured.get("failure_code", "docx_open_failed"),
                "failure_reason": structured.get("failure_reason", ""),
                "activity_status": "",
                "activity_name": "",
                "cover_mode": "",
                "attempt_no": 1,
                "claim": claim_info or {},
                "worker_config": (worker_config.to_public_dict() if worker_config else None),
            })
            monitor.update_slot(
                slot,
                cn_state("FAILED"),
                账号="百家号图文",
                文章标题=article_title,
                文档路径=str(docx_path),
                发布文件夹=str(docx_path.parent),
                封面模式="",
                活动状态="",
                活动名称="",
                总共=claim_plan_total,
                已发布=published_count,
                失败分类="docx_open_failed",
                失败原因=structured.get("failure_reason", ""),
                尝试次数=f"1/{args.max_retries + 1}",
            )
            _write_running_results(debug_root, results)
            report = _summarize_batch_results(results, total_count=claim_plan_total, max_retries=args.max_retries, mode="batch" if args.all else "single")
            _write_batch_report(debug_root, report)
            continue
        except Exception as e:
            final_summary = _build_direct_failure_result(
                docx_path=docx_path,
                article_title=article_title,
                attempt_no=1,
                failure_code="docx_read_failed",
                failure_reason=f"docx read failed: {type(e).__name__}: {e}",
            )
            archive_info = _archive_processed_docx(articles_root, docx_path, success=False, fallback_paths=fallback_paths)
            final_summary["archive"] = archive_info
            results.append(final_summary)
            structured = (final_summary or {}).get("structured_result") or {}
            _append_ledger_entry(articles_root, {
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "status": "failed",
                "worker": worker,
                "title": structured.get("title", article_title),
                "source_path": str((claim_info or {}).get("from") or ""),
                "processing_path": str(docx_path),
                "final_path": str((archive_info or {}).get("to") or ""),
                "archive": archive_info,
                "success_url": "",
                "failure_code": structured.get("failure_code", "docx_read_failed"),
                "failure_reason": structured.get("failure_reason", ""),
                "activity_status": "",
                "activity_name": "",
                "cover_mode": "",
                "attempt_no": 1,
                "claim": claim_info or {},
                "worker_config": (worker_config.to_public_dict() if worker_config else None),
            })
            monitor.update_slot(
                slot,
                cn_state("FAILED"),
                账号="百家号图文",
                文章标题=article_title,
                文档路径=str(docx_path),
                发布文件夹=str(docx_path.parent),
                封面模式="",
                活动状态="",
                活动名称="",
                总共=claim_plan_total,
                已发布=published_count,
                失败分类="docx_read_failed",
                失败原因=structured.get("failure_reason", ""),
                尝试次数=f"1/{args.max_retries + 1}",
            )
            _write_running_results(debug_root, results)
            report = _summarize_batch_results(results, total_count=claim_plan_total, max_retries=args.max_retries, mode="batch" if args.all else "single")
            _write_batch_report(debug_root, report)
            continue

        _write_worker_status(articles_root, worker, {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "worker": worker,
            "state": "processing",
            "current_docx": str(docx_path),
            "current_title": article.title,
            "run_index": idx,
            "planned_total": claim_plan_total,
            "debug_root": str(debug_root),
            "worker_config": (worker_config.to_public_dict() if worker_config else None),
        })

        _append_ledger_entry(articles_root, {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "processing",
            "worker": worker,
            "title": article.title,
            "source_path": str((claim_info or {}).get("from") or ""),
            "processing_path": str(docx_path),
            "claim": claim_info or {},
            "worker_config": (worker_config.to_public_dict() if worker_config else None),
        })

        for attempt_no in range(1, args.max_retries + 2):
            per_debug_dir = debug_root / f"run_{idx:02d}_try_{attempt_no:02d}_{docx_path.stem}"
            per_debug_dir.mkdir(parents=True, exist_ok=True)
            profile_dir = Path(args.profile) if args.profile else (debug_root / "profiles" / f"worker_{worker}")
            profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                final_summary, ok = await publish_one(
                    docx_path=docx_path,
                    slot=slot,
                    args=args,
                    monitor=monitor,
                    profile_dir=profile_dir,
                    debug_dir=per_debug_dir,
                    cookies=cookies,
                    total_count=claim_plan_total,
                    published_so_far=published_count,
                    attempt_no=attempt_no,
                    max_retries=args.max_retries,
                )
                print(json.dumps(final_summary, ensure_ascii=False, indent=2))
            finally:
                if False and not args.keep_profile and not args.profile:
                    shutil.rmtree(profile_dir, ignore_errors=True)

            if ok:
                break

            failure_code = ((final_summary or {}).get("structured_result") or {}).get("failure_code", "")
            if not _should_retry(failure_code, attempt_no, args.max_retries):
                break

            monitor.update_slot(
                slot,
                cn_state("FAILED"),
                账号="百家号图文",
                文章标题=((final_summary or {}).get("structured_result") or {}).get("title", docx_path.stem),
                文档路径=str(docx_path),
                发布文件夹=str(docx_path.parent),
                封面模式=((final_summary or {}).get("structured_result") or {}).get("cover_mode", ""),
                活动状态=((final_summary or {}).get("structured_result") or {}).get("activity_status", ""),
                活动名称=((final_summary or {}).get("structured_result") or {}).get("activity_name", ""),
                总共=claim_plan_total,
                已发布=published_count,
                失败分类=failure_code,
                失败原因=((final_summary or {}).get("structured_result") or {}).get("failure_reason", ""),
                尝试次数=f"{attempt_no}/{args.max_retries + 1}",
                说明=f"命中可重试失败，{args.retry_delay_seconds} 秒后重试",
            )
            await asyncio.sleep(max(0, args.retry_delay_seconds))

        if final_summary is None:
            continue

        archive_info = _archive_processed_docx(articles_root, docx_path, success=ok, fallback_paths=fallback_paths)
        final_summary["archive"] = archive_info
        results.append(final_summary)
        structured = (final_summary or {}).get("structured_result") or {}
        if _is_login_redirect_failure(structured, final_summary):
            structured["account_online_status"] = "offline"
            structured["failure_code"] = "account_offline"
            base_reason = str(structured.get("failure_reason") or "未稳定进入 type=news 图文编辑页")
            structured["failure_reason"] = f"{base_reason}（账号已掉线）"
            _mark_account_offline(worker, args.account_store, str(structured.get("failure_reason") or "account_offline/login_redirect"), str(structured.get("title") or article.title))
            monitor.update_slot(
                slot,
                cn_state("FAILED"),
                账号="百家号图文",
                文章标题=structured.get("title", article.title),
                文档路径=str(docx_path),
                发布文件夹=str(docx_path.parent),
                封面模式=structured.get("cover_mode", ""),
                活动状态=structured.get("activity_status", ""),
                活动名称=structured.get("activity_name", ""),
                总共=claim_plan_total,
                已发布=published_count,
                失败分类=structured.get("failure_code", "wrong_entry"),
                失败原因=structured.get("failure_reason", ""),
                账号状态="已掉线",
                说明="检测到跳转到百度登录页，已标记账号掉线",
            )
        _append_ledger_entry(articles_root, {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "success" if ok else "failed",
            "worker": worker,
            "title": structured.get("title", article.title),
            "source_path": str((claim_info or {}).get("from") or ""),
            "processing_path": str(docx_path),
            "final_path": str((archive_info or {}).get("to") or ""),
            "archive": archive_info,
            "success_url": structured.get("success_url", ""),
            "failure_code": structured.get("failure_code", ""),
            "failure_reason": structured.get("failure_reason", ""),
            "activity_status": structured.get("activity_status", ""),
            "activity_name": structured.get("activity_name", ""),
            "cover_mode": structured.get("cover_mode", ""),
            "attempt_no": structured.get("attempt_no", 1),
            "claim": claim_info or {},
            "worker_config": (worker_config.to_public_dict() if worker_config else None),
            "account_online_status": structured.get("account_online_status", ""),
        })
        _write_running_results(debug_root, results)
        report = _summarize_batch_results(results, total_count=claim_plan_total, max_retries=args.max_retries, mode="batch" if args.all else "single")
        _write_batch_report(debug_root, report)
        if ok:
            published_count += 1
            if args.success_interval_seconds > 0 and idx < claim_plan_total:
                monitor.update_slot(
                    slot,
                    cn_state("SUCCESS"),
                    账号="百家号图文",
                    文章标题=structured.get("title", article.title),
                    文档路径=str(docx_path),
                    发布文件夹=str(docx_path.parent),
                    封面模式=structured.get("cover_mode", ""),
                    活动状态=structured.get("activity_status", ""),
                    活动名称=structured.get("activity_name", ""),
                    总共=claim_plan_total,
                    已发布=published_count,
                    说明=f"发布成功，等待 {args.success_interval_seconds} 秒后继续下一篇",
                )
                await asyncio.sleep(max(0, args.success_interval_seconds))

    batch_summary = _summarize_batch_results(results, total_count=claim_plan_total, max_retries=args.max_retries, mode="batch" if args.all else "single")
    _write_running_results(debug_root, results, batch_summary=batch_summary)
    _write_batch_report(debug_root, batch_summary)
    _write_worker_status(articles_root, worker, {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "worker": worker,
        "state": "finished",
        "published": batch_summary["published"],
        "failed": batch_summary["failed"],
        "planned_total": total_count,
        "debug_root": str(debug_root),
        "worker_config": (worker_config.to_public_dict() if worker_config else None),
    })
    _clear_worker_status(articles_root, worker)
    monitor.finish(summary_text=f"batch={batch_summary['mode']} | published={batch_summary['published']}/{claim_plan_total} | retries={args.max_retries}")
    print(json.dumps(batch_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as e:
        import traceback
        debug_root = Path(r"D:\milu_publish_reverse_20260513\debug\top_level_crash")
        debug_root.mkdir(parents=True, exist_ok=True)
        (debug_root / "run_publish_draft_exception.txt").write_text(repr(e), encoding="utf-8")
        (debug_root / "run_publish_draft_traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise

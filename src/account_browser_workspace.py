from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from account_store import DEFAULT_ACCOUNT_STORE, load_account_records
from browser_publish import inject_cookies
from cookies import load_cookie_file


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE_ROOT = REPO_ROOT / "runtime" / "account_manager"
DEFAULT_WORKSPACE_PROFILE = DEFAULT_WORKSPACE_ROOT / "browser_workspace"
DEFAULT_WORKSPACE_STATE = DEFAULT_WORKSPACE_ROOT / "browser_workspace_state.json"
DEFAULT_HOME_URL = "https://baijiahao.baidu.com/builder/rc/home"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "worker"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)


def _cookie_file_path(worker_name: str) -> Path:
    return DEFAULT_WORKSPACE_ROOT / "cookies" / f"{_safe_name(worker_name)}.txt"


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"accounts": {}, "last_updated": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("accounts", {})
            return data
    except Exception:
        pass
    return {"accounts": {}, "last_updated": ""}


def _save_state(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["last_updated"] = _now_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def _ensure_page(context: BrowserContext, account_title: str) -> Page:
    pages = context.pages
    for page in pages:
        try:
            title = await page.title()
        except Exception:
            title = ""
        if title == account_title:
            return page
    page = await context.new_page()
    await page.set_extra_http_headers({"X-OpenClaw-Account": account_title})
    return page


async def open_account_tab(worker_name: str, store_path: Path, workspace_profile: Path, state_path: Path, home_url: str) -> dict:
    accounts = load_account_records(store_path)
    target = next((item for item in accounts if item.worker_name == worker_name), None)
    if target is None:
        raise RuntimeError(f"账号库中找不到 worker: {worker_name}")
    if not target.ck:
        raise RuntimeError(f"账号缺少 CK: {worker_name}")

    cookie_file = _cookie_file_path(worker_name)
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookie_file.write_text(target.ck, encoding="utf-8")
    cookies = load_cookie_file(cookie_file)

    state = _load_state(state_path)
    state_accounts = state.setdefault("accounts", {})

    async with async_playwright() as p:
        edge_executable = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        launch_kwargs = {
            "headless": False,
            "viewport": {"width": 1440, "height": 960},
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if edge_executable.exists():
            launch_kwargs["executable_path"] = str(edge_executable)
        else:
            launch_kwargs["channel"] = "msedge"

        context = await p.chromium.launch_persistent_context(str(workspace_profile), **launch_kwargs)
        await inject_cookies(context, cookies)

        page_title = f"账号主页 · {target.worker_name}"
        page = await _ensure_page(context, page_title)
        await page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.set_viewport_size({"width": 1440, "height": 960})
        await page.evaluate("document.title = arguments[0]", page_title)
        await page.bring_to_front()

        state_accounts[target.worker_name] = {
            "worker_name": target.worker_name,
            "account_name": target.account_name,
            "page_title": page_title,
            "home_url": home_url,
            "last_opened_at": _now_iso(),
            "online_status": "unknown",
        }
        _save_state(state_path, state)

        result = {
            "worker_name": target.worker_name,
            "account_name": target.account_name,
            "page_title": page_title,
            "home_url": page.url,
            "state_path": str(state_path),
            "workspace_profile": str(workspace_profile),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        await context.close()
        return result


async def main() -> int:
    ap = argparse.ArgumentParser(description="Open account home tabs in a shared browser workspace")
    ap.add_argument("--worker", required=True)
    ap.add_argument("--store", default=str(DEFAULT_ACCOUNT_STORE))
    ap.add_argument("--workspace-profile", default=str(DEFAULT_WORKSPACE_PROFILE))
    ap.add_argument("--state", default=str(DEFAULT_WORKSPACE_STATE))
    ap.add_argument("--url", default=DEFAULT_HOME_URL)
    args = ap.parse_args()

    await open_account_tab(
        worker_name=str(args.worker).strip(),
        store_path=Path(args.store),
        workspace_profile=Path(args.workspace_profile),
        state_path=Path(args.state),
        home_url=str(args.url).strip() or DEFAULT_HOME_URL,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

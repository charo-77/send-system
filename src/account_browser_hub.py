from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from browser_publish import inject_cookies
from cookies import parse_cookie_header


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "runtime" / "account_manager" / "browser_workspace_state.json"
HOST = "127.0.0.1"
PORT = 18765
DEFAULT_HOME_URL = "https://baijiahao.baidu.com/builder/rc/home"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class BrowserHub:
    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.playwright = None
        self.browser: Browser | None = None
        self.contexts: dict[str, BrowserContext] = {}
        self.pages: dict[str, Page] = {}
        self.state: dict = self._load_state()
        self._lock = asyncio.Lock()

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {"accounts": {}, "last_updated": ""}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("accounts", {})
                return payload
        except Exception:
            pass
        return {"accounts": {}, "last_updated": ""}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state["last_updated"] = _now_iso()
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    async def ensure_browser(self) -> Browser:
        if self.browser and self.browser.is_connected():
            return self.browser
        self.playwright = await async_playwright().start()
        edge_executable = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        launch_kwargs = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if edge_executable.exists():
            launch_kwargs["executable_path"] = str(edge_executable)
        else:
            launch_kwargs["channel"] = "msedge"
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        return self.browser

    async def classify_status(self, page: Page) -> str:
        try:
            url = page.url.lower()
        except Exception:
            return "unknown"
        if "passport.baidu.com" in url or "login" in url:
            return "offline"
        try:
            title = (await page.title()).lower()
            if "登录" in title or "login" in title:
                return "offline"
        except Exception:
            pass
        try:
            body_text = await page.evaluate("document.body ? document.body.innerText.slice(0, 1000) : ''")
            text = str(body_text or "")
            login_markers = ["登录", "手机号登录", "扫码登录", "密码登录", "请先登录"]
            if any(marker in text for marker in login_markers):
                return "offline"
        except Exception:
            pass
        return "online"

    async def guess_real_name(self, page: Page, fallback: str) -> str:
        js = """
        const selectors = [
          '[class*="name"]',
          '[class*="user"] [class*="name"]',
          'a[href*="profile"]',
          'span[class*="nickname"]'
        ];
        for (const selector of selectors) {
          const nodes = Array.from(document.querySelectorAll(selector));
          for (const node of nodes) {
            const text = (node.innerText || node.textContent || '').trim();
            if (text && text.length <= 40) return text;
          }
        }
        return '';
        """
        try:
            detected = str(await page.evaluate(js) or "").strip()
            return detected or fallback
        except Exception:
            return fallback

    async def open_account(self, worker_name: str, account_name: str, ck: str, home_url: str) -> dict:
        async with self._lock:
            await self.ensure_browser()
            existing_page = self.pages.get(worker_name)
            if existing_page is not None and existing_page.is_closed():
                self.pages.pop(worker_name, None)
                stale_context = self.contexts.pop(worker_name, None)
                if stale_context is not None:
                    try:
                        await stale_context.close()
                    except Exception:
                        pass
                existing_page = None
            if existing_page is not None and not existing_page.is_closed():
                try:
                    await existing_page.bring_to_front()
                except Exception:
                    pass
                status = await self.classify_status(existing_page)
                real_name = self.state.get("accounts", {}).get(worker_name, {}).get("real_name") or account_name or worker_name
                self.state.setdefault("accounts", {})[worker_name] = {
                    "worker_name": worker_name,
                    "nickname": worker_name,
                    "real_name": real_name,
                    "online_status": status,
                    "last_opened_at": _now_iso(),
                    "page_mode": "reused",
                }
                self._save_state()
                return {"ok": True, "worker_name": worker_name, "reused": True, "online_status": status, "real_name": real_name}

            browser = await self.ensure_browser()
            context = await browser.new_context(viewport={"width": 1440, "height": 960})
            cookies = parse_cookie_header(ck)
            await inject_cookies(context, cookies)
            page = await context.new_page()
            await page.goto(home_url or DEFAULT_HOME_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1200)
            status = await self.classify_status(page)
            real_name = await self.guess_real_name(page, account_name or worker_name)
            self.contexts[worker_name] = context
            self.pages[worker_name] = page
            self.state.setdefault("accounts", {})[worker_name] = {
                "worker_name": worker_name,
                "nickname": worker_name,
                "real_name": real_name,
                "online_status": status,
                "last_opened_at": _now_iso(),
                "page_mode": "opened",
            }
            self._save_state()
            try:
                await page.bring_to_front()
            except Exception:
                pass
            return {"ok": True, "worker_name": worker_name, "reused": False, "online_status": status, "real_name": real_name}

    async def ping(self) -> dict:
        await self.ensure_browser()
        return {"ok": True, "connected": True, "accounts": list(self.pages.keys())}


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, hub: BrowserHub):
    try:
        raw = await reader.readline()
        request = json.loads(raw.decode("utf-8")) if raw else {}
        action = str(request.get("action") or "").strip()
        if action == "ping":
            response = await hub.ping()
        elif action == "open_account":
            response = await hub.open_account(
                worker_name=str(request.get("worker_name") or "").strip(),
                account_name=str(request.get("account_name") or "").strip(),
                ck=str(request.get("ck") or "").strip(),
                home_url=str(request.get("home_url") or DEFAULT_HOME_URL).strip() or DEFAULT_HOME_URL,
            )
        else:
            response = {"ok": False, "error": f"unknown action: {action}"}
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
    writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def main() -> int:
    hub = BrowserHub(STATE_PATH)
    server = await asyncio.start_server(lambda r, w: handle_client(r, w, hub), HOST, PORT)
    async with server:
        await server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

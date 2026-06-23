from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDateTime, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from account_store import AccountRecord, now_iso, save_account_records
from cookies import parse_cookie_header
from qt_request_sniffer import QtRequestSniffer


REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_ROOT = REPO_ROOT / "runtime" / "account_manager" / "qt_profiles"
DEFAULT_HOME_URL = "https://baijiahao.baidu.com/builder/rc/home"
STATE_PATH = REPO_ROOT / "runtime" / "account_manager" / "browser_workspace_state.json"

HIGH_CONF_NAME_ENDPOINTS = {
    "/user-ui/cms/settingInfo",
    "/author/eco/complain/getExtInfo",
}

STRUCTURED_QUERY_ENDPOINTS = {
    "/author/eco/statistic/getauthorhistory",
    "/author/eco/income4/homepageincome",
    "/author/eco/statistics/appStatisticV2",
    "/pcui/article/lists",
}


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (text or "").strip()) or "worker"


SNAPSHOT_JS = r"""
(() => {
  const bodyText = document.body ? document.body.innerText : '';
  const compact = text => (text || '').replace(/\s+/g, ' ').trim();
  const findByKeywords = (keywords) => {
    const nodes = Array.from(document.querySelectorAll('div, span, p, strong, em, a, li, td'));
    for (const node of nodes) {
      const text = compact(node.innerText || node.textContent || '');
      if (!text || text.length > 100) continue;
      if (keywords.every(keyword => text.includes(keyword))) return text;
    }
    return '';
  };
  const loginMarkers = ['登录', '手机号登录', '扫码登录', '密码登录', '请先登录'];
  const offline = loginMarkers.some(marker => bodyText.includes(marker));

  return {
    offline,
    orgName: findByKeywords(['机构']) || findByKeywords(['归属']) || '',
    yesterdayIncome: findByKeywords(['昨日', '收益']) || findByKeywords(['昨日收益']) || '',
    pageText: compact(bodyText).slice(0, 3000),
  };
})();
"""


class AccountWebView(QWebEngineView):
    statusChanged = pyqtSignal(str, str, str)
    snapshotChanged = pyqtSignal(str, dict)

    def __init__(self, account: AccountRecord, accounts: list[AccountRecord], parent=None):
        super().__init__(parent)
        self.account = account
        self.accounts = accounts
        self.profile_dir = PROFILE_ROOT / _safe_name(account.worker_name)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        cache_path = self.profile_dir / "cache"
        storage_path = self.profile_dir / "storage"
        self.profile = QWebEngineProfile(account.worker_name, self)
        self.profile.setPersistentStoragePath(str(storage_path))
        self.profile.setCachePath(str(cache_path))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.interceptor = QtRequestSniffer(self)
        self.profile.setUrlRequestInterceptor(self.interceptor)

        self.page_obj = QWebEnginePage(self.profile, self)
        self.setPage(self.page_obj)

        self.loadStarted.connect(self._on_load_started)
        self.loadFinished.connect(self._on_load_finished)
        self.urlChanged.connect(self._on_url_changed)
        self.page_obj.renderProcessTerminated.connect(self._on_render_process_terminated)

        self._is_loading = False
        self._last_open_ms = 0
        self._api_probe_urls: set[str] = set()
        self._api_tokens: dict[str, str] = {}
        self._last_probe_payload: dict[str, Any] = {}

        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(120000)
        self.monitor_timer.timeout.connect(self.refresh_monitor_snapshot)

    def open_home(self):
        now_ms = QDateTime.currentMSecsSinceEpoch()
        if self._is_loading and now_ms - self._last_open_ms < 2500:
            return
        if now_ms - self._last_open_ms < 1200:
            return
        self._last_open_ms = now_ms
        self._is_loading = True
        self._inject_ck()
        self.load(QUrl(DEFAULT_HOME_URL))

    def refresh_monitor_snapshot(self):
        if self._is_loading:
            return
        if not self.url().toString():
            return
        self._collect_snapshot()

    def _inject_ck(self):
        store = self.profile.cookieStore()
        cookies = parse_cookie_header(self.account.ck or "")
        for item in cookies:
            for domain in [".baidu.com", ".baijiahao.baidu.com", ".baijiahao.com"]:
                cookie = QNetworkCookie()
                cookie.setName(item.name.encode("utf-8"))
                cookie.setValue(item.value.encode("utf-8"))
                cookie.setDomain(domain)
                cookie.setPath(item.path or "/")
                cookie.setSecure(True)
                store.setCookie(cookie, QUrl("https://baijiahao.baidu.com/"))

    def _status_from_url(self, url: str) -> str:
        text = (url or "").lower()
        if "passport.baidu.com" in text or "login" in text:
            return "offline"
        if "baijiahao.baidu.com" in text:
            return "online"
        return "unknown"

    def _load_state_payload(self) -> dict:
        payload = {"accounts": {}, "last_updated": now_iso()}
        if STATE_PATH.exists():
            try:
                old = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(old, dict):
                    payload.update(old)
                    payload.setdefault("accounts", {})
            except Exception:
                pass
        return payload

    def _save_snapshot(self, snapshot: dict):
        payload = self._load_state_payload()
        payload["last_updated"] = now_iso()
        payload["accounts"][self.account.worker_name] = snapshot
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.snapshotChanged.emit(self.account.worker_name, snapshot)

    def _apply_real_name(self, real_name: str):
        text = str(real_name or "").strip()
        if not text:
            return
        if len(text) < 2 or len(text) > 24:
            return
        if text in {"99+", "44", "55", "66", "77", "88"}:
            return
        if not any("\u4e00" <= ch <= "\u9fff" or ch.isalpha() for ch in text):
            return
        if text != self.account.real_name:
            self.account.real_name = text
            self.account.updated_at = now_iso()
            save_account_records(self.accounts)

    def _remember_api_url(self, url: str):
        if any(path in url for path in HIGH_CONF_NAME_ENDPOINTS) or any(path in url for path in STRUCTURED_QUERY_ENDPOINTS):
            self._api_probe_urls.add(url)

    def remember_api_token(self, url: str, token: str):
        clean_url = str(url or "").strip()
        clean_token = str(token or "").strip()
        if not clean_url or not clean_token:
            return
        if any(path in clean_url for path in HIGH_CONF_NAME_ENDPOINTS) or any(path in clean_url for path in STRUCTURED_QUERY_ENDPOINTS):
            self._api_tokens[clean_url] = clean_token

    def _extract_name_from_api_payload(self, api_url: str, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        data = payload.get("data")
        if not isinstance(data, dict):
            return ""
        if "/user-ui/cms/settingInfo" in api_url:
            return str(data.get("name") or "").strip()
        if "/author/eco/complain/getExtInfo" in api_url:
            return str(data.get("account_name") or "").strip()
        return ""

    def _merge_probe_payload(self, probe: dict[str, Any]):
        changed = False
        for key, value in probe.items():
            if not value:
                continue
            if self._last_probe_payload.get(key) != value:
                self._last_probe_payload[key] = value
                changed = True
        return changed

    def _probe_high_confidence_fields(self):
        urls = sorted(self._api_probe_urls)
        if not urls:
            self._persist_snapshot()
            return

        script = """
            (async (jobs) => {
              const out = [];
              for (const job of jobs) {
                try {
                  const headers = {
                    'x-requested-with': 'XMLHttpRequest',
                    'accept': 'application/json, text/plain, */*',
                  };
                  if (job.token) headers['token'] = job.token;
                  const resp = await fetch(job.url, {
                    credentials: 'include',
                    headers,
                    referrer: job.referrer || location.href,
                  });
                  const text = await resp.text();
                  out.push({ url: job.url, ok: resp.ok, status: resp.status, text });
                } catch (err) {
                  out.push({ url: job.url, ok: false, status: 0, error: String(err || '') });
                }
              }
              return out;
            })
        """

        def on_result(value):
            records = value if isinstance(value, list) else []
            probe: dict[str, Any] = {}
            for item in records:
                if not isinstance(item, dict):
                    continue
                api_url = str(item.get("url") or "")
                text = str(item.get("text") or "")
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                real_name = self._extract_name_from_api_payload(api_url, payload)
                if real_name:
                    probe["real_name_source"] = api_url
                    probe["real_name_confidence"] = "high"
                    probe["real_name"] = real_name
                    self._apply_real_name(real_name)
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, dict):
                    if "/user-ui/cms/settingInfo" in api_url:
                        probe["org_name"] = str(data.get("org_name") or "").strip()
                    if "/author/eco/complain/getExtInfo" in api_url:
                        probe["account_status"] = str(data.get("account_status") or "").strip()
                    if "/author/eco/statistic/getauthorhistory" in api_url:
                        total = data.get("total") if isinstance(data.get("total"), dict) else {}
                        probe["activity_value"] = str(total.get("view_count") or "").strip()
                        probe["publish_count_total"] = str(total.get("publish_count") or "").strip()
                    if "/author/eco/statistics/appStatisticV2" in api_url:
                        total = data.get("total") if isinstance(data.get("total"), dict) else {}
                        probe["activity_value"] = str(total.get("view_count") or probe.get("activity_value") or "").strip()
                        probe["publish_count_total"] = str(total.get("publish_count") or probe.get("publish_count_total") or "").strip()
                        probe["fans_increase"] = str(total.get("fans_increase") or "").strip()
                    if "/author/eco/income4/homepageincome" in api_url:
                        core = data.get("coreData") if isinstance(data.get("coreData"), dict) else {}
                        common = data.get("commonData") if isinstance(data.get("commonData"), dict) else {}
                        probe["yesterday_income"] = str(core.get("yesterdayIncome") or "").strip()
                        probe["fans_total"] = str(core.get("fansCount") or "").strip()
                        probe["max_publish_number"] = str(common.get("maxPublishNumber") or "").strip()
                    if "/pcui/article/lists" in api_url:
                        article_list = data.get("list") if isinstance(data.get("list"), list) else []
                        today_prefix = QDateTime.currentDateTime().toString("yyyy-MM-dd")
                        today_published = 0
                        for article in article_list:
                            if not isinstance(article, dict):
                                continue
                            publish_time = str(article.get("publish_time") or article.get("commit_at") or "").strip()
                            status = str(article.get("status") or "").strip().lower()
                            is_published = int(article.get("is_published") or 0)
                            if publish_time.startswith(today_prefix) and (status == "publish" or is_published == 1):
                                today_published += 1
                        probe["today_published_count"] = str(today_published)
            self._merge_probe_payload(probe)
            self._persist_snapshot()

        jobs = [{"url": url, "token": self._api_tokens.get(url, ""), "referrer": self.url().toString()} for url in urls]
        self.page_obj.runJavaScript(script, on_result, 0, jobs)

    def _persist_snapshot(self, payload: dict[str, Any] | None = None):
        status = self.account.online_status or self._status_from_url(self.url().toString())
        payload = payload or {}
        snapshot = {
            "worker_name": self.account.worker_name,
            "nickname": self.account.worker_name,
            "real_name": self.account.real_name or self.account.account_name or self.account.worker_name,
            "real_name_confidence": self._last_probe_payload.get("real_name_confidence") or "none",
            "real_name_source": self._last_probe_payload.get("real_name_source") or "",
            "online_status": status,
            "last_opened_at": self.account.last_opened_at or now_iso(),
            "page_mode": "embedded",
            "url": self.url().toString(),
            "checked_at": now_iso(),
            "org_name": str(payload.get("orgName") or self._last_probe_payload.get("org_name") or "").strip(),
            "yesterday_income": str(payload.get("yesterdayIncome") or "").strip(),
            "publish_quota": "",
            "page_text_sample": str(payload.get("pageText") or "").strip(),
            "activity_value": str(self._last_probe_payload.get("activity_value") or "").strip(),
            "publish_count_total": str(self._last_probe_payload.get("publish_count_total") or "").strip(),
            "fans_increase": str(self._last_probe_payload.get("fans_increase") or "").strip(),
            "fans_total": str(self._last_probe_payload.get("fans_total") or "").strip(),
            "max_publish_number": str(self._last_probe_payload.get("max_publish_number") or "").strip(),
            "today_published_count": str(self._last_probe_payload.get("today_published_count") or "").strip(),
            "yesterday_income": str(self._last_probe_payload.get("yesterday_income") or payload.get("yesterdayIncome") or "").strip(),
            "probe_urls": sorted(self._api_probe_urls),
        }
        if self._last_probe_payload.get("account_status"):
            snapshot["account_status"] = self._last_probe_payload["account_status"]
        self._save_snapshot(snapshot)
        self.statusChanged.emit(self.account.worker_name, status, snapshot["real_name"])

    def _collect_snapshot(self):
        def on_snapshot(value):
            payload = value if isinstance(value, dict) else {}
            status = "offline" if payload.get("offline") else self._status_from_url(self.url().toString())
            self.account.online_status = status
            self.account.updated_at = now_iso()
            save_account_records(self.accounts)
            self._persist_snapshot(payload)
            if status != "offline":
                self._probe_high_confidence_fields()

        self.page_obj.runJavaScript(SNAPSHOT_JS, on_snapshot)

    def _on_load_started(self):
        self._is_loading = True

    def _on_load_finished(self, ok: bool):
        self._is_loading = False
        status = self._status_from_url(self.url().toString()) if ok else "offline"
        self.account.online_status = status
        self.account.last_opened_at = now_iso()
        save_account_records(self.accounts)
        self._persist_snapshot()
        if ok and status != "offline":
            self._collect_snapshot()
            self.monitor_timer.start()
            self.parent().accountReady.emit(self.account.worker_name)

    def _on_url_changed(self, url: QUrl):
        status = self._status_from_url(url.toString())
        self.account.online_status = status
        self._persist_snapshot()

    def _on_render_process_terminated(self, termination_status, exit_code):
        self._is_loading = False
        self.account.online_status = "offline"
        snapshot = {
            "render_process_exit_code": int(exit_code),
            "render_process_status": str(termination_status),
        }
        self._persist_snapshot(snapshot)
        self.setHtml("<html><body style='font-family:Segoe UI;padding:24px;color:#203047;background:#ffffff;'><h3>页面进程已退出</h3><p>这个账号页刚刚崩了，可以再点一次“打开账号主页”重开。</p></body></html>")
        self.statusChanged.emit(self.account.worker_name, "offline", self.account.real_name or self.account.account_name or self.account.worker_name)


class EmbeddedBrowserTabs(QWidget):
    statusChanged = pyqtSignal(str, str, str)
    snapshotChanged = pyqtSignal(str, dict)
    accountReady = pyqtSignal(str)

    def __init__(self, accounts: list[AccountRecord], parent=None):
        super().__init__(parent)
        self.accounts = accounts
        self.views: dict[str, AccountWebView] = {}

        layout = QVBoxLayout(self)
        self.empty_label = QLabel("双击左侧账号后，在这里打开内嵌主页")
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.tabs, 1)

    def open_account(self, account: AccountRecord):
        existing = self.views.get(account.worker_name)
        if existing is not None:
            idx = self.tabs.indexOf(existing)
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)
                return
        view = AccountWebView(account, self.accounts, self)
        view.statusChanged.connect(self.statusChanged.emit)
        view.snapshotChanged.connect(self.snapshotChanged.emit)
        title = account.real_name or account.account_name or account.worker_name
        idx = self.tabs.addTab(view, title)
        self.tabs.setCurrentIndex(idx)
        self.views[account.worker_name] = view
        self.empty_label.setVisible(False)
        view.open_home()

    def refresh_open_accounts(self):
        for view in self.views.values():
            view.refresh_monitor_snapshot()

    def close_tab(self, index: int):
        widget = self.tabs.widget(index)
        if widget is None:
            return
        worker_name = getattr(widget, "account", None).worker_name if hasattr(widget, "account") else None
        self.tabs.removeTab(index)
        widget.deleteLater()
        if worker_name:
            self.views.pop(worker_name, None)
        if self.tabs.count() == 0:
            self.empty_label.setVisible(True)

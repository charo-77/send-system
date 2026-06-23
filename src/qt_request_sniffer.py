from __future__ import annotations

from PyQt6.QtCore import QObject
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor


class QtRequestSniffer(QWebEngineUrlRequestInterceptor):
    def __init__(self, owner: QObject):
        super().__init__(owner)
        self.owner = owner

    def interceptRequest(self, info: QWebEngineUrlRequestInfo):
        try:
            url = info.requestUrl().toString()
        except Exception:
            return
        if not url:
            return
        token = ""
        try:
            for raw in info.requestHeaders():
                name = bytes(raw).decode("utf-8", errors="ignore").lower()
                if name != "token":
                    continue
                value = bytes(info.requestHeader(raw)).decode("utf-8", errors="ignore")
                token = value.strip()
                break
        except Exception:
            token = ""
        if hasattr(self.owner, "_remember_api_url"):
            self.owner._remember_api_url(url)
        if token and hasattr(self.owner, "remember_api_token"):
            self.owner.remember_api_token(url, token)

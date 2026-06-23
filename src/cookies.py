from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List
from urllib.parse import unquote


@dataclass
class CookieItem:
    name: str
    value: str
    domain: str = ""
    path: str = "/"


def parse_cookie_header(text: str) -> List[CookieItem]:
    items: List[CookieItem] = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        items.append(CookieItem(name=name.strip(), value=unquote(value.strip())))
    return items


def load_cookie_file(path: Path) -> List[CookieItem]:
    return parse_cookie_header(path.read_text(encoding="utf-8", errors="ignore"))

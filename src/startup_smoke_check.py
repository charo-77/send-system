from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from account_manager_qt import AccountManagerWindow  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    window = AccountManagerWindow()
    print({
        "window": type(window).__name__,
        "accounts": len(getattr(window, "accounts", []) or []),
        "has_embedded_tabs": bool(getattr(window, "embedded_tabs", None)),
        "has_query_btn": bool(getattr(window, "query_btn", None)),
        "has_publish_btn": bool(getattr(window, "publish_btn", None)),
    })
    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

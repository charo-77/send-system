from __future__ import annotations

import time
from pathlib import Path

import win32com.client


def begin_copy_docx_body_to_clipboard(path: Path, visible: bool = False, wait_seconds: float = 1.0):
    """Open Word/WPS, copy full document body, and KEEP the source app alive.

    Office/WPS often places delayed-render formats on the clipboard. If the source
    document/app is closed before Chrome pastes, HTML/RTF/images can vanish and the
    editor receives an empty paragraph. Caller must close via close_clipboard_source().
    """
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    app = win32com.client.DispatchEx("Word.Application")
    app.Visible = bool(visible)
    app.DisplayAlerts = 0
    doc = app.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
    doc.Activate()
    app.Selection.WholeStory()
    app.Selection.Copy()
    time.sleep(wait_seconds)
    return app, doc, {"copied": True, "path": str(path), "visible": visible, "source_kept_open": True}


def close_clipboard_source(app, doc) -> None:
    try:
        if doc is not None:
            doc.Close(False)
    finally:
        if app is not None:
            app.Quit()


def copy_docx_body_to_clipboard(path: Path, visible: bool = False, wait_seconds: float = 1.0) -> dict:
    app = doc = None
    try:
        app, doc, info = begin_copy_docx_body_to_clipboard(path, visible=visible, wait_seconds=wait_seconds)
        return info
    finally:
        close_clipboard_source(app, doc)

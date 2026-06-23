from __future__ import annotations

import win32clipboard


def _build_cf_html(fragment: str, source_url: str = "") -> bytes:
    """Build Windows CF_HTML payload for the standard 'HTML Format' clipboard format."""
    html = (
        "<html><head><meta charset=\"utf-8\"></head><body>"
        "<!--StartFragment-->"
        + fragment
        + "<!--EndFragment-->"
        "</body></html>"
    )
    prefix_template = (
        "Version:0.9\r\n"
        "StartHTML:{start_html:010d}\r\n"
        "EndHTML:{end_html:010d}\r\n"
        "StartFragment:{start_fragment:010d}\r\n"
        "EndFragment:{end_fragment:010d}\r\n"
    )
    if source_url:
        prefix_template += f"SourceURL:{source_url}\r\n"
    dummy = prefix_template.format(start_html=0, end_html=0, start_fragment=0, end_fragment=0)
    html_bytes = html.encode("utf-8")
    dummy_bytes = dummy.encode("utf-8")
    start_html = len(dummy_bytes)
    end_html = start_html + len(html_bytes)
    start_fragment = start_html + len(html[: html.index("<!--StartFragment-->") + len("<!--StartFragment-->")].encode("utf-8"))
    end_fragment = start_html + len(html[: html.index("<!--EndFragment-->")].encode("utf-8"))
    header = prefix_template.format(
        start_html=start_html,
        end_html=end_html,
        start_fragment=start_fragment,
        end_fragment=end_fragment,
    )
    return header.encode("utf-8") + html_bytes


def set_html_clipboard(fragment: str, plain_text: str = "") -> dict:
    fmt_html = win32clipboard.RegisterClipboardFormat("HTML Format")
    payload = _build_cf_html(fragment)
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(fmt_html, payload)
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, plain_text or fragment)
    finally:
        win32clipboard.CloseClipboard()
    return {"html_clipboard": True, "html_bytes": len(payload), "text_chars": len(plain_text or fragment)}

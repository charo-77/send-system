import traceback
try:
    import sys
    from pathlib import Path
    sys.path.insert(0, r'D:\milu_publish_reverse_20260513\src')
    print("[1] imports done")
    from cookies import load_cookie_file as load_cookies
    print("[2] cookies loaded")
    from browser_publish import inject_cookies as inject_cookies_func
    print("[3] browser_publish injected")
    print(f"inject_cookies_func = {inject_cookies_func}")
except Exception as e:
    traceback.print_exc()
    print(f"ERROR: {e}")
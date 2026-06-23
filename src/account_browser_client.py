from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from account_store import DEFAULT_ACCOUNT_STORE, load_account_records


REPO_ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
PORT = 18765
DEFAULT_HOME_URL = "https://baijiahao.baidu.com/builder/rc/home"


async def send_request(payload: dict) -> dict:
    reader, writer = await asyncio.open_connection(HOST, PORT)
    writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()
    raw = await reader.readline()
    writer.close()
    await writer.wait_closed()
    if not raw:
        return {"ok": False, "error": "empty response"}
    return json.loads(raw.decode("utf-8"))


async def ensure_hub_ready() -> None:
    try:
        await send_request({"action": "ping"})
        return
    except Exception:
        pass
    cmd = [sys.executable, str(Path(__file__).with_name("account_browser_hub.py"))]
    subprocess.Popen(cmd, cwd=str(REPO_ROOT))
    for _ in range(10):
        try:
            await asyncio.sleep(0.5)
            await send_request({"action": "ping"})
            return
        except Exception:
            continue


async def open_account(worker_name: str, store_path: Path, home_url: str) -> dict:
    accounts = load_account_records(store_path)
    target = next((item for item in accounts if item.worker_name == worker_name), None)
    if target is None:
        raise RuntimeError(f"账号库中找不到 worker: {worker_name}")
    if not target.ck:
        raise RuntimeError(f"账号缺少 CK: {worker_name}")

    for _ in range(5):
        try:
            return await send_request(
                {
                    "action": "open_account",
                    "worker_name": target.worker_name,
                    "account_name": target.account_name,
                    "ck": target.ck,
                    "home_url": home_url,
                }
            )
        except Exception:
            await asyncio.sleep(0.8)
    return {"ok": False, "error": "browser hub not ready"}


async def main() -> int:
    ap = argparse.ArgumentParser(description="Open account home via shared browser hub")
    ap.add_argument("--worker", required=True)
    ap.add_argument("--store", default=str(DEFAULT_ACCOUNT_STORE))
    ap.add_argument("--url", default=DEFAULT_HOME_URL)
    args = ap.parse_args()

    await ensure_hub_ready()
    result = await open_account(str(args.worker).strip(), Path(args.store), str(args.url).strip() or DEFAULT_HOME_URL)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

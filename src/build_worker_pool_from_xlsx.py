from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker_pool_xlsx import load_worker_configs


def psq(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build worker config files and launch scripts from CK.xlsx")
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--articles", required=True, help="pool root containing 待发布/处理中/A发布成功/A发布失败")
    ap.add_argument("--debug-root", default=r"D:\milu_publish_reverse_20260513\debug\worker_pool")
    ap.add_argument("--out-dir", default=r"D:\milu_publish_reverse_20260513\runtime\worker_pool")
    ap.add_argument("--url", default="https://baijiahao.baidu.com/builder/rc/edit?type=news")
    ap.add_argument("--activity", action="append", default=[])
    ap.add_argument("--max-workers", type=int, default=None)
    ap.add_argument("--recover-processing", action="store_true")
    ap.add_argument("--visible", action="store_true", help="do not add --headless")
    ap.add_argument("--keep-open-on-failure", action="store_true")
    ap.add_argument("--keep-open-after-success", action="store_true")
    ap.add_argument("--keep-profile", action="store_true")
    ap.add_argument("--max-retries", type=int, default=1)
    ap.add_argument("--retry-delay-seconds", type=int, default=5)
    args = ap.parse_args()

    items = load_worker_configs(Path(args.xlsx), args.sheet)
    if args.max_workers is not None:
        items = items[: max(0, args.max_workers)]
    if not items:
        raise SystemExit("no usable workers found in xlsx")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir = out_dir / "configs"
    script_dir = out_dir / "scripts"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    script_dir.mkdir(parents=True, exist_ok=True)

    public_items = []
    launch_lines = [
        "$ErrorActionPreference = 'Stop'",
        "$root = Split-Path -Parent $MyInvocation.MyCommand.Path",
        "$repo = Split-Path -Parent $root",
    ]

    for item in items:
        cfg_path = cfg_dir / f"{item.worker_name}.json"
        cfg = {
            "row": item.row,
            "account_name": item.account_name,
            "worker_name": item.worker_name,
            "proxy_mode": item.proxy_mode,
            "proxy_ip": item.proxy_ip,
            "proxy_port": item.proxy_port,
            "proxy_username": item.proxy_username,
            "proxy_password": item.proxy_password,
            "group_name": item.group_name,
            "fingerprint_id": item.fingerprint_id,
            "ck": item.ck,
        }
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        public_items.append({k: v for k, v in cfg.items() if k != "ck"} | {"ck_len": len(item.ck or "")})

        cmd_parts = [
            "python",
            ".\\src\\run_publish_draft.py",
            "--all",
            "--submit",
            f"--articles {psq(args.articles)}",
            f"--worker {psq(item.worker_name)}",
            f"--worker-config-xlsx {psq(args.xlsx)}",
            f"--debug-dir {psq(str(Path(args.debug_root) / item.worker_name))}",
            f"--url {psq(args.url)}",
            f"--max-retries {args.max_retries}",
            f"--retry-delay-seconds {args.retry_delay_seconds}",
        ]
        if args.sheet:
            cmd_parts.append(f"--worker-config-sheet {psq(args.sheet)}")
        if args.recover_processing:
            cmd_parts.append("--recover-processing")
        if args.keep_open_on_failure:
            cmd_parts.append("--keep-open-on-failure")
        if args.keep_open_after_success:
            cmd_parts.append("--keep-open-after-success")
        if args.keep_profile:
            cmd_parts.append("--keep-profile")
        if not args.visible:
            cmd_parts.append("--headless")
        for act in args.activity:
            cmd_parts.append(f"--activity {psq(act)}")

        one_script = script_dir / f"launch_{item.worker_name}.ps1"
        one_script.write_text(
            "\n".join([
                "$ErrorActionPreference = 'Stop'",
                f"Set-Location {psq(str(Path('D:/milu_publish_reverse_20260513')))}",
                "& " + " ".join(cmd_parts),
            ]) + "\n",
            encoding="utf-8",
        )

        launch_lines.append(
            "Start-Process powershell -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-File',"
            + psq(str(one_script))
            + ")"
        )

    (out_dir / "workers.public.json").write_text(json.dumps(public_items, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "launch_all_workers.ps1").write_text("\n".join(launch_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "out_dir": str(out_dir),
        "worker_count": len(public_items),
        "workers": public_items,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

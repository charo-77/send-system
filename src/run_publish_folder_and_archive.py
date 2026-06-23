from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path

from articles import extract_docx_article, extract_docx_images, list_docx
from cookies import load_cookie_file
from browser_publish import publish_draft

SUCCESS_TEXT = "提交成功，正在审核中"
SUCCESS_DIRNAME = "A成功发布"
FAIL_DIRNAME = "A失败发布"


def move_docx(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists():
        shutil.move(str(src), str(dest))
        return dest
    stem = src.stem
    suffix = src.suffix
    i = 2
    while True:
        candidate = dest_dir / f"{stem}__{i}{suffix}"
        if not candidate.exists():
            shutil.move(str(src), str(candidate))
            return candidate
        i += 1


def is_publish_success(result: dict) -> bool:
    if bool(result.get("published")):
        return True
    page_state = result.get("page_state") or {}
    body = page_state.get("body_snippet") or ""
    if SUCCESS_TEXT in body:
        return True
    submit = result.get("submit") or {}
    markers = submit.get("success_markers") or []
    if any("submitted-reviewing" in str(x) for x in markers):
        return True
    return False


async def publish_one(docx_path: Path, args, cookies) -> dict:
    article = extract_docx_article(docx_path)
    debug_root = Path(args.debug_dir)
    per_doc_dir = debug_root / docx_path.stem
    docx_images = extract_docx_images(docx_path, per_doc_dir / "covers")
    result = await publish_draft(
        article=article,
        cookies=cookies,
        user_data_dir=Path(args.profile_root) / docx_path.stem,
        url=args.url,
        headless=args.headless,
        submit=True,
        debug_dir=per_doc_dir,
        cover_path=(docx_images[0] if docx_images else None),
        docx_path=docx_path,
        docx_image_count=len(docx_images),
        activity_names=args.activity,
    )
    return result


async def main() -> int:
    ap = argparse.ArgumentParser(description="Publish all docx in a folder, then archive to A成功发布 / A失败发布")
    ap.add_argument("--articles", required=True, help="Root folder containing docx files")
    ap.add_argument("--cookie-file", default=r"D:\milu_publish_reverse_20260513\ck.txt")
    ap.add_argument("--url", default=None)
    ap.add_argument("--profile-root", default=r"D:\milu_publish_reverse_20260513\edge_profiles_batch")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--debug-dir", default=r"D:\milu_publish_reverse_20260513\debug\batch_archive_runs")
    ap.add_argument("--limit", type=int, default=0, help="0 means all")
    ap.add_argument("--activity", action="append", default=[], help="Activity name to select before publish; repeatable")
    args = ap.parse_args()

    root = Path(args.articles)
    success_dir = root / SUCCESS_DIRNAME
    fail_dir = root / FAIL_DIRNAME

    files = [p for p in list_docx(root) if SUCCESS_DIRNAME not in p.parts and FAIL_DIRNAME not in p.parts]
    if args.limit and args.limit > 0:
        files = files[: args.limit]
    if not files:
        raise SystemExit("no docx files found")

    cookies = load_cookie_file(Path(args.cookie_file))
    summary = []

    for idx, docx_path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] publishing: {docx_path}")
        try:
            result = await publish_one(docx_path, args, cookies)
            ok = is_publish_success(result)
            target_dir = success_dir if ok else fail_dir
            moved_to = move_docx(docx_path, target_dir)
            row = {
                "source": str(docx_path),
                "moved_to": str(moved_to),
                "success": ok,
                "published": bool(result.get("published")),
                "page_url": (result.get("page_state") or {}).get("url"),
                "body_snippet": (result.get("page_state") or {}).get("body_snippet", "")[:500],
            }
            summary.append(row)
            print(json.dumps(row, ensure_ascii=False))
        except Exception as e:
            moved_to = move_docx(docx_path, fail_dir)
            row = {
                "source": str(docx_path),
                "moved_to": str(moved_to),
                "success": False,
                "error": str(e),
            }
            summary.append(row)
            print(json.dumps(row, ensure_ascii=False))

    out = Path(args.debug_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"done": True, "total": len(summary), "summary": str(out / 'summary.json')}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

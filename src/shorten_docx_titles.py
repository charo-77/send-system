from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_API_BASE = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M3"
SKIP_DIRS = {"A发布成功", "A发布失败", "发布监控", "处理中", ".claim_locks"}
INVALID_FILENAME_CHARS = r'<>:"/\\|?*'

USER_PROMPT = """# 标题精简改写提示词
请把冗长平淡的原文长标题/开篇首段，精简改写为20字以内吸睛短标题
1. 严守事实、绝不夸大造谣，保留核心主旨
2. 剔除废话口水话，语气简洁抓眼球
3. 风格百搭适配图文推文，短句利落好点击
4. 严格控制单条标题≤20个字，多产出3-5组不同风格备选
5. 拒绝生硬直译，优化语序提升阅读吸引力

直接粘贴原文长内容即可生成。
"""


def visible_len(text: str) -> int:
    return len(text.strip())




TITLE_PREFIX_RE = re.compile(
    r"^((?:\d{6,}|\d{4}[-_]?\d{2}[-_]?\d{2}[-_]?\d{0,6})(?:__|[_\-\s]+)|(?:[A-Za-z0-9]+__)+|(?:[^_\\/]{1,30}__)+|(?:\d+[._、\-\s]+))+"
)


def normalize_article_title(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("　", " ")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = TITLE_PREFIX_RE.sub("", text)
    parts = text.split("__")
    if len(parts) >= 4 and re.fullmatch(r"\d{8}_\d{6}_\d+", parts[0] or ""):
        text = parts[-1]
    elif len(parts) >= 3 and parts[0].isdigit():
        text = parts[-1]
    text = re.sub(r"^[A-Za-z0-9_-]{1,32}__", "", text)
    text = re.sub(r"^\d+[._、\-\s]+", "", text)
    text = re.sub(r"[\x00-\x1f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" _-，。；：、【】[]()（）《》<>") or str(value or "").strip()


def clean_processing_stem(stem: str) -> str:
    return normalize_article_title(stem)


def sanitize_filename_stem(text: str, max_chars: int) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    text = re.sub(r"[\r\n\t]+", " ", text).strip()
    text = text.strip(" 《》“”‘’'\".,，。:：;；!！?？-_— ")
    text = "".join("_" if ch in INVALID_FILENAME_CHARS else ch for ch in text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"_+", "_", text).strip("_ ")
    if not text:
        text = "短标题"
    return text[:max_chars].rstrip("_ -，。；：、") or text[:max_chars]


def iter_docx(root: Path) -> list[Path]:
    files: list[Path] = []
    root = root.resolve()
    for path in root.rglob("*.docx"):
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            continue
        try:
            rel_parts = path.resolve().relative_to(root).parts[:-1]
        except ValueError:
            rel_parts = path.parts[:-1]
        # Skip generated subfolders, but do not skip the selected root itself if it is named A????/A????.
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        files.append(path)
    return sorted(files)


def unique_target(path: Path, new_stem: str) -> Path:
    target = path.with_name(new_stem + path.suffix)
    if target.resolve() == path.resolve():
        return target
    index = 2
    while target.exists():
        target = path.with_name(f"{new_stem}_{index}{path.suffix}")
        index += 1
    return target


def chat_completion(api_base: str, api_key: str, model: str, prompt: str, timeout: int = 60) -> str:
    base = api_base.rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文图文推文标题编辑。必须严格执行用户给的标题精简改写提示词。"
                    "输出3-5行备选标题，每行一个标题，不要解释，不要编号。"
                    "每条标题必须≤20个字，真实、有可读性、吸引人点击。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"].strip()
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    return content


def parse_candidates(raw: str, max_chars: int) -> list[str]:
    candidates: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.、)]|[一二三四五][.、)])\s*", "", line).strip()
        if not line:
            continue
        title = sanitize_filename_stem(line, max_chars)
        if title and visible_len(title) <= max_chars and title not in candidates:
            candidates.append(title)
    if not candidates:
        fallback = sanitize_filename_stem(raw, max_chars)
        if fallback:
            candidates.append(fallback)
    return candidates


def shorten_title(api_base: str, api_key: str, model: str, title: str, max_chars: int, retries: int = 2) -> tuple[str, list[str], str]:
    prompt = f"{USER_PROMPT}\n\n原文长内容：\n{title}\n\n请输出3-5个不同风格备选标题，每行一个。"
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            raw = chat_completion(api_base, api_key, model, prompt)
            candidates = parse_candidates(raw, max_chars)
            return candidates[0], candidates, raw
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2 + attempt * 2)
    raise RuntimeError(str(last_error) if last_error else "unknown API error")


def main() -> int:
    parser = argparse.ArgumentParser(description="Use MiniMax AI to shorten long .docx filenames only; docx content is never modified.")
    parser.add_argument("--root", required=True, help="Folder containing docx files")
    parser.add_argument("--threshold", type=int, default=64, help="Only shorten filenames greater than or equal to this many chars")
    parser.add_argument("--max-chars", type=int, default=20, help="AI short title max chars")
    parser.add_argument("--api-base", default=os.getenv("MINIMAX_API_BASE", os.getenv("CST9_API_BASE", DEFAULT_API_BASE)))
    parser.add_argument("--model", default=os.getenv("MINIMAX_MODEL", os.getenv("CST9_MODEL", DEFAULT_MODEL)))
    parser.add_argument("--api-key", default=os.getenv("MINIMAX_API_KEY", os.getenv("CST9_API_KEY", "")))
    parser.add_argument("--apply", action="store_true", help="Actually rename files. Without this, dry-run only.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files processed")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent API workers")
    parser.add_argument("--quiet", action="store_true", help="Print less output")
    parser.add_argument("--report", default="", help="Write jsonl report path")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR root not found: {root}", file=sys.stderr)
        return 2
    if args.threshold <= args.max_chars:
        print("ERROR --threshold should be larger than --max-chars", file=sys.stderr)
        return 2
    if not args.api_key:
        print("ERROR missing API key. Set MINIMAX_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    candidates = []
    for path in iter_docx(root):
        title = clean_processing_stem(path.stem)
        if visible_len(title) >= args.threshold:
            candidates.append((path, title))
    if args.limit > 0:
        candidates = candidates[: args.limit]

    print(f"root={root}")
    print("content=NOT_MODIFIED filenames_only=true")
    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'} threshold={args.threshold} max_chars={args.max_chars} candidates={len(candidates)}")

    report_fh = None
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_fh = report_path.open("a", encoding="utf-8")

    changed = 0
    failed = 0
    workers = max(1, int(args.workers or 1))

    def process_one(index: int, path: Path, old_title: str) -> dict:
        short_title, all_candidates, raw = shorten_title(args.api_base, args.api_key, args.model, old_title, args.max_chars)
        target = unique_target(path, short_title)
        applied = False
        if args.apply and target.resolve() != path.resolve():
            path.rename(target)
            applied = True
        return {
            "ok": True,
            "applied": bool(args.apply),
            "renamed": applied,
            "index": index,
            "from": str(path),
            "to": str(target),
            "old_title": old_title,
            "new_title": short_title,
            "raw": raw,
        }

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(process_one, index, path, old_title): (index, path, old_title)
                for index, (path, old_title) in enumerate(candidates, start=1)
            }
            for future in as_completed(futures):
                index, path, old_title = futures[future]
                try:
                    item = future.result()
                    if item.get("renamed"):
                        changed += 1
                    if not args.quiet:
                        print(f"[{index}/{len(candidates)}] {old_title} -> {item['new_title']}")
                    elif item.get("renamed"):
                        print(f"[{index}/{len(candidates)}] renamed -> {item['new_title']}")
                    if report_fh:
                        report_fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                        report_fh.flush()
                except Exception as exc:
                    failed += 1
                    item = {"ok": False, "index": index, "from": str(path), "old_title": old_title, "error": str(exc)}
                    print(f"[{index}/{len(candidates)}] FAILED {path.name}: {exc}", file=sys.stderr)
                    if report_fh:
                        report_fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                        report_fh.flush()
    finally:
        if report_fh:
            report_fh.close()

    print(f"done candidates={len(candidates)} changed={changed} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

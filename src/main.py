from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from articles import extract_docx_article, list_docx
from cookies import load_cookie_file


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", required=True, help="docx folder")
    parser.add_argument("--cookie-file", required=True, help="cookie/session text file")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    article_root = Path(args.articles)
    cookie_path = Path(args.cookie_file)

    articles = list_docx(article_root)[: args.limit]
    cookies = load_cookie_file(cookie_path)

    print(f"articles={len(articles)} cookies={len(cookies)}")
    for a in articles:
        art = extract_docx_article(a)
        print("TITLE:", art.title)
        print("PATH:", art.path)
        print("BODY_LEN:", len(art.body))
        print("---")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

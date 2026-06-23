from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

base = Path(r"D:\milu_publish_reverse_20260513")
sys.path.insert(0, str(base / 'src'))

from articles import list_docx, extract_docx_article
from cookies import load_cookie_file
from browser_publish import publish_draft

CK = base / 'ck.txt'
ARTICLES = Path(r"C:\Users\Administrator\Desktop\mingming\国际")

async def main():
    outdir = base / 'debug' / 'run_publish_submit_single'
    outdir.mkdir(parents=True, exist_ok=True)

    cookies = load_cookie_file(CK)
    files = list_docx(ARTICLES)
    if not files:
        raise SystemExit('no docx files found')
    docx = files[0]
    article = extract_docx_article(docx)

    result = await publish_draft(
        article=article,
        cookies=cookies,
        user_data_dir=base / f'edge_profile_publish_submit_single_{int(time.time())}',
        submit=True,
        debug_dir=outdir,
        docx_path=docx,
        docx_image_count=1,
        headless=False,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    asyncio.run(main())

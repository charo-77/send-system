from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import List
from zipfile import ZipFile
import shutil

from docx import Document


@dataclass
class Article:
    path: Path
    title: str
    body: str
    body_html: str = ""


def _para_has_content(para) -> bool:
    if para.text and para.text.strip():
        return True
    return bool(getattr(para._element, 'xpath', lambda *_: [])('.//*[local-name()="blip"]'))


def _para_to_html(para, rel_to_dataurl: dict[str, str]) -> str:
    parts: list[str] = []
    for run in para.runs:
        text = escape(run.text or "")
        if text:
            if run.bold:
                text = f"<strong>{text}</strong>"
            if run.italic:
                text = f"<em>{text}</em>"
            if run.underline:
                text = f"<u>{text}</u>"
            parts.append(text)
        # inline images in the same run
        blips = getattr(run._element, 'xpath', lambda *_: [])('.//*[local-name()="blip"]')
        for blip in blips:
            rid = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
            if rid and rid in rel_to_dataurl:
                parts.append(f'<img src="{rel_to_dataurl[rid]}" />')
    return "<p>" + ("".join(parts) if parts else "<br>") + "</p>"


def _docx_image_relmap(doc: Document, path: Path) -> dict[str, str]:
    relmap: dict[str, str] = {}
    with ZipFile(path) as z:
        for rel in doc.part.rels.values():
            try:
                target = str(rel.target_ref)
                if 'image' not in target:
                    continue
                name = target if target.startswith('word/') else f'word/{target}'
                data = z.read(name)
                mime = mimetypes.guess_type(name)[0] or 'image/png'
                relmap[rel.rId] = f"data:{mime};base64," + base64.b64encode(data).decode('ascii')
            except Exception:
                continue
    return relmap


def _clean_processing_stem(stem: str) -> str:
    # Processing files are renamed like: 20260621_111204_233860__??8__15936_xxx__Original_Title
    # Never use the timestamp/worker prefix as the article title.
    parts = stem.split("__")
    if len(parts) >= 4 and parts[0].isdigit():
        return parts[-1].strip("_ ") or stem
    return stem


def extract_docx_article(path: Path) -> Article:
    doc = Document(str(path))
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    # Prefer the first non-empty paragraph as title; if unavailable, strip processing prefixes from filename.
    title = paras[0] if paras else _clean_processing_stem(path.stem)
    body_paras = paras[1:] if len(paras) > 1 else []
    body = "\n\n".join(body_paras or paras)
    relmap = _docx_image_relmap(doc, path)
    body_html = "\n".join(_para_to_html(p, relmap) for p in doc.paragraphs if _para_has_content(p))
    return Article(path=path, title=title, body=body, body_html=body_html)


def extract_docx_images(path: Path, out_dir: Path) -> list[Path]:
    """Extract embedded docx images in order for cover selection/upload."""
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix_map = {
        ".jpeg": ".jpg",
        ".jpg": ".jpg",
        ".png": ".png",
        ".webp": ".webp",
    }
    outs: list[Path] = []
    with ZipFile(path) as z:
        media = sorted(n for n in z.namelist() if n.startswith("word/media/"))
        for idx, name in enumerate(media, start=1):
            ext = Path(name).suffix.lower()
            if ext not in suffix_map:
                continue
            out = out_dir / f"{path.stem}_img{idx:02d}{suffix_map[ext]}"
            out.write_bytes(z.read(name))
            outs.append(out)
    return outs


def extract_first_docx_image(path: Path, out_dir: Path) -> Path | None:
    """Extract the first embedded docx image for use as Baijiahao cover."""
    imgs = extract_docx_images(path, out_dir)
    return imgs[0] if imgs else None


def list_docx(root: Path) -> List[Path]:
    skipped_dirs = {"A发布成功", "A发布失败"}
    return sorted([
        p for p in root.rglob("*.docx")
        if p.is_file() and not any(part in skipped_dirs for part in p.parts)
    ])

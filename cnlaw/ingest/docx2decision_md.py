"""Convert patent invalidation decision .docx files into corpus Markdown.

The decision corpus (``无效复审决定/*.md``) is parsed by :mod:`parse_decision`,
which expects plain-text paragraphs plus 2-cell ``| label | value |`` table rows
and no Markdown bold / pandoc artifacts. ``python-docx`` yields exactly that:
each body paragraph becomes one text paragraph and each table row becomes a
pipe-joined line, so the parser reads the fields directly.

This module reads ``.docx`` files — either from a directory or directly from a
``.zip`` archive (streamed from memory, so no intermediate docx is written). It
handles the degraded 202603 archive whose folder name is mojibake by deriving the
output filename from the *basename* only (the docx basenames are ASCII), skips
non-``.docx`` members (e.g. the ``.xlsx`` in 202603), and writes one ``.md`` per
decision plus a ``_conversion_summary.json``.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _iter_body(doc: Document):
    """Yield ('p', paragraph) / ('tbl', table) for the document body in order."""
    for el in doc.element.body:
        tag = el.tag.split("}")[-1]
        if tag == "p":
            yield "p", Paragraph(el, doc)
        elif tag == "tbl":
            yield "tbl", Table(el, doc)


def _cell_text(cell) -> str:
    """Join the paragraph texts of a table cell, preserving cell '：' labels."""
    texts = [p.text.strip() for p in cell.paragraphs]
    # A standalone control paragraph that is empty contributes nothing.
    return " ".join(t for t in texts if t)


def _row_cells(row) -> List[str]:
    """Return the text of every cell in a table row.

    Full-width merged cells repeat their content across the grid columns, and the
    corpus convention is to keep those duplicates (the parser relies on a
    ``| 决定要点：… | 决定要点：… |`` row to read the inline ``label：value``), so
    the cells are NOT deduplicated here.
    """
    return [_cell_text(c) for c in row.cells]


def convert_docx(data: bytes) -> str:
    """Convert one in-memory .docx to corpus Markdown."""
    doc = Document(io.BytesIO(data))
    blocks: List[str] = []
    for kind, obj in _iter_body(doc):
        if kind == "p":
            text = obj.text.strip()
            if text:
                blocks.append(text)
        else:
            for row in obj.rows:
                cells = _row_cells(row)
                if any(cells):
                    blocks.append(" | ".join(cells))
    return "\n\n".join(blocks)


def _decoded_name(name: str) -> str:
    """Best-effort recovery of a zip member name that was cp437-mangled.

    Windows-created archives store non-ASCII names as bytes that Python decodes
    as cp437, producing mojibake. Re-encoding back and decoding as gbk/utf-8
    usually recovers the real folder name. The docx *basename* is ASCII, so
    failures still leave a usable basename.
    """
    for enc in ("gbk", "utf-8"):
        try:
            recovered = name.encode("cp437").decode(enc)
            return recovered
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return name


def iter_docx(source: Path) -> List[Tuple[str, bytes]]:
    """Return ``(basename, bytes)`` for every .docx in a zip or a directory."""
    source = Path(source)
    items: List[Tuple[str, bytes]] = []
    if source.is_dir():
        for f in sorted(source.glob("*.docx")):
            items.append((f.name, f.read_bytes()))
        return items

    with zipfile.ZipFile(source) as zf:
        for info in zf.infolist():
            raw = info.filename
            name = os.path.basename(_decoded_name(raw) or raw)
            if not name.lower().endswith(".docx"):
                continue
            if name.startswith("."):
                continue
            items.append((name, zf.read(info)))

    return items


def convert_source(source: Path, output: Path, limit: int | None = None) -> Dict:
    """Convert all docx in ``source`` into ``output`` as .md."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    items = iter_docx(source)
    summary: Dict = {"total": len(items), "success": 0, "failed": 0, "errors": []}

    for i, (name, data) in enumerate(items):
        if limit is not None and i >= limit:
            summary["total"] = i
            break
        md = None
        try:
            md = convert_docx(data)
            if not md.strip():
                raise ValueError("Empty text after conversion")
            out_path = output / f"{Path(name).stem}.md"
            out_path.write_text(md, encoding="utf-8")
            summary["success"] += 1
        except Exception as e:  # noqa: BLE001 - report, don't hide a bad docx
            summary["failed"] += 1
            summary["errors"].append({"source": name, "error": str(e)[:200]})

    summary_path = output / "_conversion_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Convert patent invalidation docx -> corpus Markdown.")
    parser.add_argument("--input", required=True, help="A .zip archive or a directory of .docx files.")
    parser.add_argument("--output", required=True, help="Directory to write the .md files.")
    parser.add_argument("--limit", type=int, default=None, help="Only convert the first N files (smoke).")
    args = parser.parse_args(argv)

    summary = convert_source(Path(args.input), Path(args.output), args.limit)
    print(
        {
            "total": summary["total"],
            "success": summary["success"],
            "failed": summary["failed"],
        }
    )
    if summary["errors"]:
        print("sample_errors:", summary["errors"][:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

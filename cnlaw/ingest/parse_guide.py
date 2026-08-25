"""Parse the normalized 专利审查指南 chapter corpus into LawDocument objects.

The guide has no 第N条 structure; its logical unit is a numbered section under a
chapter (部分 -> 章 -> 节 -> 小节 -> 子小节). This parser turns each numbered
heading of a chapter markdown into a :Article-shaped ``LawArticle`` whose
``number`` is the section path (e.g. ``2.1``, ``3.1.2``) and which carries the
hierarchy metadata (level, part, chapter, parent) so the existing graph loader
can persist it. ``LawArticle`` keeps a ``text`` body and an optional ``title``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .parse_laws import LawArticle, LawDocument

# section heading: ### 1 引言 / #### 2.1 ... / ##### 3.1.1 ... (## is the chapter)
_SECTION_RE = re.compile(r"^(#{3,})\s+(\d+(?:\.\d+)*)\s+(.+)$")
_CH_TITLE_RE = re.compile(r"^##\s+第([一二三四五六七八九十]+)章\s*(.*)$")
_PART_RE = re.compile(r"^专利审查指南\s*第([一二三四五六七八九十]+)部分")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
           "八": 8, "九": 9, "十": 10}
_CN_MAP = {v: k for k, v in _CN_NUM.items()}

_INTRO_NUMBER = "0"  # chapter-level introductory text node


def _level(m: re.Match) -> int:
    return len(m.group(1)) - 2  # ### -> 1, #### -> 2, ##### -> 3


def _parent(number: str) -> str:
    return number.rsplit(".", 1)[0] if "." in number else ""


def _clean(text: str) -> str:
    return re.sub(r"\*\*", "", text).strip()


def _is_section_head(title: str) -> bool:
    """True if ``title`` is a real section heading, not prose that merely begins
    with a number (e.g. an inline '第N.M节' cross-reference or an OCR list item).
    Real headings are short noun phrases and never carry sentence punctuation
    ('。，；：！？'); an enumeration comma ('、') is allowed."""
    if not re.match(r"^[\u4e00-\u9fff]", title):
        return False
    if re.search(r"[。，；：！？]", title):
        return False
    return True


def parse_guide_markdown(path, category: str = "审查指南", domain: str = "专利",
                         legal_level: str = "部门规章", source_date: Optional[str] = "2023-12-11") -> LawDocument:
    """Parse one chapter markdown file into a LawDocument of numbered sections."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    text = "\n".join(lines)

    full_name = next((m.group(1).strip() for line in lines if (m := re.match(r"^#\s+(.+)$", line))), path.stem)
    pm = _PART_RE.match(full_name)
    part_cn = pm.group(1) if pm else ""
    cm = next((m for line in lines if (m := _CH_TITLE_RE.match(line))), None)
    chapter_cn = cm.group(1) if cm else ""
    chapter_title = cm.group(2).strip() if cm else ""

    articles: List[LawArticle] = []
    cur: Optional[LawArticle] = None
    intro: List[str] = []

    def flush():
        if cur is not None:
            t = "\n".join(_clean(l) for l in cur.text.split("\n") if _clean(l)).strip()
            if t:  # a bare container heading (no prose of its own) is dropped
                cur.text = t
                articles.append(cur)

    saw_section = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        sm = _SECTION_RE.match(s)
        if sm:
            title = sm.group(3)
            if _is_section_head(title):
                flush()
                number = sm.group(2)
                cur = LawArticle(
                    number=number,
                    text="",
                    title=_clean(title),
                    level=_level(sm),
                    part=part_cn,
                    chapter=chapter_title,
                    parent_number=_parent(number),
                )
                saw_section = True
                continue
            # pseudo-heading: prose that happens to begin with "N.M " (e.g. an
            # inline '第N.M节' reference or a numbered list item). Re-join its
            # text to the current body instead of creating a spurious node.
            prose = re.sub(r"^#{3,}\s+\d+(?:\.\d+)*\s+", "", s).strip()
            if cur is not None:
                cur.text = (cur.text + "\n" + prose).strip()
            elif not saw_section:
                intro.append(prose)
            continue
        if cur is not None:
            cur.text = (cur.text + "\n" + s).strip()
        elif not saw_section:
            # intro zone (before the first section): drop headings/comments, keep prose
            if re.match(r"^#{1,}", s) or re.match(r"^<!--", s):
                continue
            intro.append(s)

    flush()  # emit the trailing section that the loop's last match left open

    # chapter-level intro (before the first section) as a "0" node, if any prose
    intro = [l for l in ("\n".join(intro)).split("\n") if _clean(l)]
    if intro:
        intro_text = "\n".join(_clean(l) for l in intro)
        articles.insert(0, LawArticle(number=_INTRO_NUMBER, text=intro_text,
                                      title="本章引言", level=0, part=part_cn,
                                      chapter=chapter_title, parent_number="",
                                      kind="introduction"))
    for a in articles:
        a.kind = a.kind or "guideline_section"

    base = re.sub(r"\.md$", "", path.name)
    return LawDocument(
        name=chapter_title or base,
        full_name=full_name,
        category=category,
        domain=domain,
        legal_level=legal_level,
        status="现行有效",
        source_date=source_date,
        path=str(path),
        file_name=path.name,
        articles=articles,
    )


def scan_guide_corpus(root) -> List[LawDocument]:
    """Parse every chapter markdown under a normalized guide corpus directory."""
    root = Path(root)
    docs = []
    for f in sorted(root.glob("*.md")):
        docs.append(parse_guide_markdown(f))
    return docs


_AMENDMENT_RE = re.compile(r"^###\s+(\d+)\.\s+(.+)$")


def parse_amendment_markdown(path, category: str = "审查指南", domain: str = "专利",
                             legal_level: str = "部门规章", source_date: str = "2026-01-01",
                             name: str = "专利审查指南修改对照表") -> LawDocument:
    """Parse 修改对照表.md into a LawDocument of per-modification-point articles.

    Each ``### <seq>. <reference>`` block is one amendment article whose text
    concatenates the 旧版（2023） and 新版（2026） blocks. It is ingested as a
    separate searchable document (not merged into the 2023 base text).
    """
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    full_name = next((m.group(1).strip() for line in lines if (m := re.match(r"^#\s+(.+)$", line))), name)

    articles: List[LawArticle] = []
    cur: Optional[LawArticle] = None

    def flush():
        if cur is not None:
            t = "\n".join(_clean(l) for l in cur.text.split("\n") if _clean(l)).strip()
            if t:
                cur.text = t
                articles.append(cur)

    for line in lines:
        s = line.strip()
        if not s:
            continue
        m = _AMENDMENT_RE.match(s)
        if m:
            flush()
            cur = LawArticle(number=m.group(1), text="", title=_clean(m.group(2)),
                             kind="amendment")
            continue
        if re.match(r"^##\s", s):  # a `##` section/part marker, not a mod point
            continue
        if cur is not None:
            cur.text = (cur.text + "\n" + s.lstrip(">").strip()).strip()
    flush()

    return LawDocument(
        name=name,
        full_name=full_name,
        category=category,
        domain=domain,
        legal_level=legal_level,
        status="现行有效",
        source_date=source_date,
        path=str(path),
        file_name=path.name,
        articles=articles,
    )

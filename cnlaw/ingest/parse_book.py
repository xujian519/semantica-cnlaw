"""Parse the 以案说法 (patent review / invalidation typical-cases) book corpus.

The extracted per-chapter ``第X章-*.txt`` files under ``书籍/extracted/`` are a
scan of the book 以案说法：专利复审、无效典型案例指引. Each chapter becomes a
``LegalDocument`` and each numbered "要点" section (1, 1.1, 1.1.1, ...) becomes
an :Article-shaped ``LawArticle`` (``kind='book_section'``) whose ``number`` is
the section path, mirroring how the 审查指南 guide corpus is modeled.

The source is OCR text, so section numbers carry stray whitespace and OCR glyph
errors (``l``/``I`` for ``1``, fullwidth dots, trailing junction marks); those
are normalised before the section path and level are derived. Chapter intro
prose (before the first section) is emitted as a ``0`` introduction node, and
running headers / page footers are dropped, exactly as the guide parser does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .parse_laws import LawArticle, LawDocument

BOOK_NAME = "以案说法"
BOOK_FULL_TITLE = "《以案说法：专利复审、无效典型案例指引》"
BOOK_DATE = "2018-09-01"
BOOK_LEVEL = "书籍"

EXTRACT_ROOT = Path("/Users/xujian/projects/宝宸知识库_Raw/书籍/extracted")

_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
       "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}

# A heading line: optional number with dotted segments, then whitespace, title.
# The number may be OCR-mangled: spaces around the dot, fullwidth dot, and the
# glyph l/I read in place of a trailing 1 (e.g. "4. 4. l 现有设计状况的考量").
_SECTION_RE = re.compile(r"^\s*([0-9lI]+(?:(?:\s*[.．]\s*)[0-9lI]+)*)\s+(\S.*)$")
_CH_HEAD_RE = re.compile(r"^\s*第([一二三四五六七八九十]+)章\s*(.*)$")
_FILE_CH_RE = re.compile(r"第([一二三四五六七八九十]+)章")


def _norm_num(num: str) -> str:
    """Normalise an OCR section number to a dotted path like '1.2.3'."""
    s = num.replace("l", "1").replace("I", "1").replace("．", ".")
    s = re.sub(r"\s*\.\s*", ".", s)          # collapse spaces around dot
    s = s.strip(".]、）)。，")
    return s


def _is_head_title(title: str) -> bool:
    """True if ``title`` reads like a real section heading, not prose.

    A heading is a short CJK noun phrase without sentence punctuation. Quotation
    marks / parentheses around a phrase are fine; an enumeration comma (、) is
    allowed. Prose that merely begins with a numeral (a claim or case line) is
    rejected because it carries sentence punctuation or is too long.
    """
    t = re.sub(r"\s+", "", title)
    if not (1 <= len(t) <= 40):
        return False
    if not re.search(r"[\u4e00-\u9fff]", t):
        return False
    # Reject prose: sentence punctuation, enumeration commas, stray ASCII the OCR
    # let through (product names / chemical formulas), and a leftover number
    # fragment ("l", "4.1") at the head of an otherwise-real title.
    if re.search(r"[。，；：！？、]", t):
        return False
    if re.search(r"[A-Za-z]", t):
        return False
    if re.match(r"^[\d.lI]", t):
        return False
    if re.fullmatch(r"[\d.、，；：！？()（）《》“”《》]+", t):
        return False
    return True


def _match_section(line: str) -> Optional[tuple]:
    """Return (depth, number, title) if ``line`` is a section heading."""
    m = _SECTION_RE.match(line)
    if not m:
        return None
    num = _norm_num(m.group(1))
    if not re.fullmatch(r"\d+(?:\.\d+)*", num):
        return None
    title = m.group(2).strip()
    if not _is_head_title(title):
        return None
    return len(num.split(".")), num, title


def _is_noise(line: str) -> bool:
    """Drop running headers, page footers and stray margin chars."""
    s = line.strip()
    if not s:
        return True
    if re.fullmatch(r"\d{1,4}", s):                     # page number footer
        return True
    if re.fullmatch(r"[（(]?\d{1,3}[-－]\d{1,3}[)）]?", s):
        return True
    if "咖气" in s or "复审、无效典型案例指引" in s:     # running header
        return True
    if re.fullmatch(r"目\s*录", s):
        return True
    if s.endswith("＇") or s in {"。", "，＇", "＇"}:     # header/body fragment
        return True
    if re.fullmatch(r"[—－]{2,}", s):
        return True
    return False


def parse_book_txt(path, category: str = "书籍", domain: str = "专利",
                   legal_level: str = BOOK_LEVEL, source_date: str = BOOK_DATE) -> LawDocument:
    """Parse one chapter txt into a LawDocument of numbered sections."""
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()

    chapter_cn = ""
    chapter_title = ""
    for line in lines:
        m = _CH_HEAD_RE.match(line)
        if m:
            chapter_cn = m.group(1)
            chapter_title = m.group(2).strip()
            break
    if not chapter_cn:
        m = _FILE_CH_RE.search(path.stem)
        if m:
            chapter_cn = m.group(1)
        chapter_title = re.sub(r"^第[一二三四五六七八九十]+章[- ]*", "", path.stem)

    articles: List[LawArticle] = []
    cur: Optional[LawArticle] = None
    intro: List[str] = []

    def flush():
        nonlocal cur
        if cur is not None:
            t = "\n".join(l for l in cur.text.split("\n") if l.strip()).strip()
            if t:
                cur.text = t
                articles.append(cur)
        cur = None

    for line in lines:
        s = line.strip()
        if _is_noise(s):
            continue
        sm = _match_section(s)
        if sm:
            depth, num, title = sm
            flush()
            cur = LawArticle(
                number=num,
                text="",
                title=title,
                level=depth,
                part=chapter_cn,
                chapter=chapter_title,
                parent_number=num.rsplit(".", 1)[0] if "." in num else "",
                kind="book_section",
            )
            continue
        if cur is not None:
            cur.text = (cur.text + "\n" + s).strip()
        elif not any(a.kind != "introduction" for a in articles) and cur is None:
            intro.append(s)

    flush()

    intro = [l for l in ("\n".join(intro)).split("\n") if l.strip()]
    if intro:
        intro_text = "\n".join(l for l in intro)
        articles.insert(0, LawArticle(number="0", text=intro_text, title="本章引言",
                                      level=0, part=chapter_cn, chapter=chapter_title,
                                      parent_number="", kind="introduction"))

    cn = _CN.get(chapter_cn, "")
    name = f"{BOOK_NAME} 第{chapter_cn}章 {chapter_title}" if chapter_cn else path.stem
    full_name = f"{BOOK_FULL_TITLE}第{chapter_cn}章 {chapter_title}" if chapter_cn else BOOK_FULL_TITLE
    return LawDocument(
        name=name,
        full_name=full_name,
        category=category,
        domain=domain,
        legal_level=legal_level,
        status="现行有效",
        source_date=source_date,
        promulgated_date=source_date,
        path=str(path),
        file_name=path.name,
        articles=articles,
    )


def scan_book(root=None) -> List[LawDocument]:
    """Parse every chapter txt under the extracted book directory, in chapter order."""
    root = Path(root) if root else EXTRACT_ROOT
    matched = [f for f in root.glob("第*章*.txt") if f.name != "全书-full.txt"]

    def key(f: Path):
        m = _FILE_CH_RE.search(f.name)
        return _CN.get(m.group(1), 99) if m else 99

    return [parse_book_txt(f) for f in sorted(matched, key=key)]

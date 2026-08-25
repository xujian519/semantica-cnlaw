"""Parse Chinese legal Markdown files into structured LawDocument objects.

The Laws-1.0.0 corpus stores each instrument as a Markdown file under a
department directory. Two shapes appear and are handled here:

  * undated: `# title -> line-by-line history -> <!-- INFO END --> -> body`
  * dated:   `# title -> single date -> <!-- INFO END --> -> bracketed
             history -> 目录 -> chapters -> body`

Obsidian markers and the INFO sentinel are stripped before article extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .exclusion import is_local_regulation

CN_NUM = "一二三四五六七八九十百千零0-9"
# 条文以 第X条 开头（可带 ** 粗体标记，如 **第一条**），可带「之N」子条后缀（如 第一百二十条之一），后跟全角/半角空格或正文
_ARTICLE_RE = re.compile(rf"^\*{{0,2}}第([{CN_NUM}]+)条(之[{CN_NUM}]+)?\*{{0,2}}[ \u3000]*(.*)$")
_YEAR_MONTH_DAY = re.compile(r"(\d{4})年(\d{1,3})月(\d{1,3})日")
_FILE_DATE_DASH = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_FILE_DATE_COMPACT = re.compile(r"[_.-](\d{4})(\d{2})(\d{2})\b")
_INFO_SENTINEL = "<!-- INFO END -->"
_TITLE_RE = re.compile(r"^#\s+(.+)$")
# 编/章/节标题、目录项等非条文行，跳过以避免误拼进条文
_SKIP_RE = re.compile(rf"^[#\-*·]\s*|^第[{CN_NUM}]+[编章节]")
_HORIZONTAL_RULE_RE = re.compile(r"^[-*]{3,}$")

# 部门目录 -> 效力层级
_CATEGORY_LEVEL = {
    "宪法": "宪法",
    "刑法": "法律",
    "民法典": "法律",
    "民法商法": "法律",
    "行政法": "法律",
    "社会法": "法律",
    "经济法": "法律",
    "宪法相关法": "法律",
    "诉讼与非诉讼程序法": "法律",
    "行政法规": "行政法规",
    "司法解释": "司法解释",
    "部门规章": "部门规章",
    "其他": "其他",
}


@dataclass
class LawArticle:
    """A single numbered article (第N条) or a guideline section (2.1.3)."""

    number: str
    text: str
    # Extra metadata used by the patent examination guide (guideline sections).
    title: str = ""
    level: int = 0
    part: str = ""
    chapter: str = ""
    parent_number: str = ""
    kind: str = ""  # "law_article" / "guideline_section" / "introduction" / "amendment"


@dataclass
class LawDocument:
    """Document-level metadata plus the parsed articles."""

    name: str
    full_name: str
    category: str
    domain: str = ""
    promulgated_date: Optional[str] = None
    amended_dates: List[str] = field(default_factory=list)
    legal_level: str = ""
    status: str = ""
    source_date: Optional[str] = None
    likely_local: bool = False
    path: str = ""
    file_name: str = ""
    articles: List[LawArticle] = field(default_factory=list)


def _strip_obsidian(text: str) -> str:
    """Drop YAML frontmatter and inline Obsidian-only markers."""
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    text = re.sub(r"bookCollapseSection", "", text)
    return text


def _to_iso(m: re.Match) -> str:
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"


def extract_dates(text: str) -> List[str]:
    """All 年/月/日 dates found in `text`, as ISO strings, in source order."""
    return [_to_iso(m) for m in _YEAR_MONTH_DAY.finditer(text)]


def extract_source_date(file_name: str) -> Optional[str]:
    """The date embedded in a filename like 刑法(2020-12-26).md or 专利法实施细则_20231211.md."""
    name = file_name or ""
    m = _FILE_DATE_DASH.search(name)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    m = _FILE_DATE_COMPACT.search(name)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}"
    return None


def _clean_article_text(text: str) -> str:
    """Strip markdown bold markers (and surrounding whitespace) from article text."""
    return re.sub(r"\*\*", "", text).strip()


def extract_articles(body: str) -> List[LawArticle]:
    """Split an article body into numbered articles.

    Each article starts at a 第N条 line (optionally wrapped in ** bold markers);
    following non-heading lines are appended to it until the next article line.
    Chapter/section headings, table-of-contents/obsidian fragments, and Markdown
    horizontal rules are skipped; blockquote markers ("> ") are stripped.
    """
    articles: List[LawArticle] = []
    cur: Optional[LawArticle] = None

    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            line = line.lstrip(">").strip()
        if _HORIZONTAL_RULE_RE.match(line):
            continue
        m = _ARTICLE_RE.match(line)
        if m:
            if cur is not None:
                articles.append(cur)
            number = f"第{m.group(1)}条" + (m.group(2) or "")
            cur = LawArticle(number=number, text=_clean_article_text(m.group(3)))
        elif cur is not None and not _SKIP_RE.match(line):
            cur.text = (cur.text + " " + _clean_article_text(line)).strip()

    if cur is not None:
        articles.append(cur)
    return articles


def classify_legal_level(category: str, full_name: str) -> str:
    """Derive the hierarchy level, preferring the department category."""
    level = _CATEGORY_LEVEL.get(category, "其他")
    if level != "其他":
        return level
    if full_name.startswith("中华人民共和国宪法"):
        return "宪法"
    if full_name.endswith("法"):
        return "法律"
    if full_name.endswith(("条例", "规定", "办法", "规则", "细则")):
        return "行政法规"
    return "其他"


def parse_law_markdown(path, category: str, domain: str = "") -> LawDocument:
    """Parse one legal Markdown file into a LawDocument.

    Args:
        path: Path to the .md file (str or Path).
        category: The department category directory the file lives in.
        domain: Optional knowledge-domain tag (e.g. '专利') for the patent corpus.
    """
    path = Path(path)
    text = _strip_obsidian(path.read_text(encoding="utf-8"))
    file_name = path.name
    lines = text.splitlines()

    # Full name: first `# title` line.
    full_name = next((m.group(1).strip() for line in lines if (m := _TITLE_RE.match(line))), "")
    if not full_name:
        full_name = path.stem

    title_idx = next((i for i, line in enumerate(lines) if _TITLE_RE.match(line)), 0)
    tail = lines[title_idx + 1 :]

    # The body starts at the first article line or the first heading, whichever
    # comes first. Everything before it (ISO-enacting/amendment history, and for
    # dated files a bracketed history paragraph, plus any preamble) is the
    # history text used to derive promulgation/amendment dates. This handles
    # flat documents (no heading after the INFO sentinel, e.g. judicial
    # interpretations) as well as the chaptered dated documents.
    body_start = len(tail)
    for i, line in enumerate(tail):
        s = line.strip()
        if s.startswith("#") or _ARTICLE_RE.match(s):
            body_start = i
            break
    history_seg = [line for line in tail[:body_start] if _INFO_SENTINEL not in line]
    history_text = "\n".join(history_seg)
    body = "\n".join(tail[body_start:])

    dates = extract_dates(history_text)
    promulgated_date = min(dates) if dates else None
    amended_dates = sorted({d for d in dates if d != promulgated_date})
    articles = extract_articles(body)

    base = re.sub(r"\.md$", "", file_name)
    base = re.sub(r"\(\d{4}-\d{2}-\d{2}\)$", "", base)
    base = re.sub(r"_\d{8}$", "", base)
    name = base or full_name
    source_date = extract_source_date(file_name)

    return LawDocument(
        name=name,
        full_name=full_name,
        category=category,
        domain=domain,
        promulgated_date=promulgated_date,
        amended_dates=amended_dates,
        legal_level=classify_legal_level(category, full_name),
        source_date=source_date,
        likely_local=is_local_regulation(full_name),
        path=str(path),
        file_name=file_name,
        articles=articles,
    )


def compute_effective_status(docs: List[LawDocument]) -> Dict[int, str]:
    """Assign effective status across versions of the same instrument.

    Confirmed 2026-08-25 policy: an undated file is treated as currently in
    force (its content matches the latest dated edition); among dated files the
    newest is current and older editions are marked superseded.
    """
    groups: Dict[str, List[LawDocument]] = {}
    for doc in docs:
        groups.setdefault(doc.full_name, []).append(doc)

    status: Dict[int, str] = {}
    for group in groups.values():
        dated = [d for d in group if d.source_date]
        latest = max(dated, key=lambda d: d.source_date) if dated else None
        for doc in group:
            if latest is None or doc.source_date is None or doc is latest:
                status[id(doc)] = "现行有效"
            else:
                status[id(doc)] = "已被修订"
    return status

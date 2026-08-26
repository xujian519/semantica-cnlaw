"""Parse Chinese IP / patent court judgment Markdown files.

The judgment corpus (``专利判决/`` + ``指导性专利判决文书_md/``) stores each court
judgment as a Markdown file with a small header and a long free-form body. Two
metadata layouts occur:

  * ``专利判决/``: a ``## 案件信息`` block of ``**field**: value`` lines followed
    by ``## 判决书正文``.
  * ``指导性专利判决文书_md/``: no section markers; a ``label\\n：\\nvalue`` header
    (case name, 审理法院, 案号, 裁判日期, 案由) then the judgment body.

The judgment type and every field are derived from the document text, never from
the filename. Extraction is pure (no database) so it is unit-testable. There is
no JSON sidecar for this corpus, so nothing is backfilled here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HORIZONTAL_RULE_RE = re.compile(r"^\s*[-*]{3,}\s*$", re.M)
# 案由的 `民事>知识产权与竞争纠纷★>...` 形式; 去掉 ★ 分隔符前的乱码
_CAUSE_CLEAN_RE = re.compile(r"[★＊*]")

# header label -> PatentJudgment field
_HEADER_FIELDS = {
    "审理法院": "court",
    "案号": "case_number",
    "案由": "cause",
    "裁判日期": "decision_date",
}

_DATE_RE = re.compile(r"(\d{4})[年.\-](\d{1,2})[月.\-](\d{1,2})日?")

# 专利号: ZL+数字, 或裸申请号 (如 94102612.4 / 200480001590.4)
_PATENT_RE = re.compile(r"ZL\s*([0-9][0-9\s]{7,}\.?[0-9]*)", re.I)
_PATENT_LABEL_RE = re.compile(r"专利(?:申请号|号)[：:]\s*([0-9][0-9\s]{7,}\.?[0-9]*)")
# 发明名称 / 专利权人 (名称为"…" / 发明名称为"…")
_INVENTION_RE = re.compile(r"(?:发明名称|名称)[为是]\s*[“\"]([^”\"]{2,80})[”\"]")
_HOLDER_RE = re.compile(r"([^\s，。；;、]{2,40}?)(?:是|系)[^。]{0,80}?的专利权人")
# 案由中的案件类型: 民事/行政/刑事
_CASE_KIND = (
    (("民事判决书", "民事裁定书", "民事调解书"), "民事"),
    (("行政判决书", "行政裁定书", "行政裁定"), "行政"),
    (("刑事判决书", "刑事裁定书"), "刑事"),
)

# 正文分隔标记 (form A only)
_BODY_MARKER = "## 判决书正文"
_META_MARKER = "## 案件信息"


@dataclass
class PatentJudgment:
    """A single parsed court judgment on a patent / IP dispute."""

    judgment_id: str = ""  # 案号,fallback source_file
    case_number: str = ""  # 案号
    case_type: str = ""  # 民事/行政/刑事/待核验
    cause: str = ""  # 案由
    court: str = ""  # 审理法院
    decision_date: str = ""  # 裁判日期 (ISO)
    invention_name: str = ""
    patent_holder: str = ""
    plaintiff: str = ""
    defendant: str = ""
    panel: str = ""
    legal_basis: str = ""
    decision_points: str = ""
    decision_result: str = ""
    claims: str = ""
    legal_reasoning: str = ""
    application_number: str = ""  # 主诉专利号
    patent_numbers: List[str] = field(default_factory=list)  # 全部涉及专利号
    domain: str = "专利判决"
    source_path: str = ""
    source_file: str = ""
    file_name: str = ""
    full_text: str = ""
    confidence: str = ""


def _normalize_date(s: Optional[str]) -> str:
    """Normalize a noisy date string to ISO YYYY-MM-DD, or ''."""
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    m = _DATE_RE.search(s)
    if not m:
        return ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def _normalize_case_number(s: Optional[str]) -> str:
    """Unify parens and drop internal whitespace; canonicalise a case number.

    e.g. （2010）浦民三（知）初字第249 号 -> (2010)浦民三(知)初字第249号.
    """
    if not s:
        return ""
    s = re.sub(r"[（【\[(]", "(", s)
    s = re.sub(r"[）】\])]", ")", s)
    s = re.sub(r"\s+", "", s)
    return s


def _grab_label(text: str, label: str) -> str:
    """Extract the value following a header label in any of the common layouts.

    Handles ``**label**: value``, ``label：value`` and the newline-separated
    ``label\\n：\\nvalue`` form used by the 指导性 corpus.
    """
    # 换行分隔: label \n ： \n value  (label 与 ： 之间允许换行)
    m = re.search(rf"{label}\s*\**\s*[：:]\**\s*([^\n]+)", text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_header_meta(text: str) -> Dict[str, str]:
    """Pull the header metadata (court / case_number / cause / date)."""
    meta: Dict[str, str] = {}
    # A-format: restrict to the 案件信息 block; otherwise scan the doc head.
    region = text
    if _META_MARKER in text:
        start = text.find(_META_MARKER)
        end = text.find(_BODY_MARKER, start) if _BODY_MARKER in text else start + 3000
        region = text[start:end]
    else:
        region = text[:3000]

    for label, field_name in _HEADER_FIELDS.items():
        v = _grab_label(region, label)
        if not v:
            continue
        if field_name == "decision_date":
            iso = _normalize_date(v)
            if iso:
                meta[field_name] = iso
        elif field_name == "case_number":
            cn = _normalize_case_number(v)
            if cn:
                meta[field_name] = cn
        else:
            meta[field_name] = _CAUSE_CLEAN_RE.sub("", v)
    return meta


def _detect_case_type(text: str, cause: str = "") -> str:
    """Derive 民事/行政/刑事 from the cause-of-action prefix or the doc type."""
    c = (cause or "").strip()
    if c.startswith("民事") or "民事>" in c[:12]:
        return "民事"
    if c.startswith("行政") or "行政>" in c[:12]:
        return "行政"
    if c.startswith("刑事") or "刑事>" in c[:12]:
        return "刑事"
    head = text[:2000]
    for markers, kind in _CASE_KIND:
        if any(m in head for m in markers):
            return kind
    return "待核验"


def _extract_patent_numbers(text: str) -> Tuple[str, List[str]]:
    """Return (primary_number, all_number) where numbers are bare (no ZL)."""
    found: List[str] = []
    for pat in (_PATENT_RE, _PATENT_LABEL_RE):
        for m in re.finditer(pat, text):
            raw = re.sub(r"\s+", "", m.group(1))
            raw = raw.rstrip(".")
            if raw:
                found.append(raw)
    # 去重并保序
    seen = set()
    nums: List[str] = []
    for n in found:
        if n not in seen:
            seen.add(n)
            nums.append(n)
    return (nums[0] if nums else ""), nums


def _extract_invention_name(text: str) -> str:
    m = _INVENTION_RE.search(text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_patent_holder(text: str) -> str:
    m = _HOLDER_RE.search(text)
    if not m:
        return ""
    val = m.group(1).strip()
    # 去掉行首角色词, 保留单位名
    val = re.sub(r"^(?:原告|被告|上诉人|被上诉人|申请再审人|被申请人|申请人|请求人)+", "", val)
    return val.strip() or ""


def _extract_parties(text: str) -> Tuple[str, str]:
    """Best-effort plaintiff/appellant and defendant/appellee."""
    plaintiff = defendant = ""
    head = text[:3000]
    for role, is_p in (("原告", True), ("上诉人", True), ("申请再审人", True),
                       ("被告", False), ("被上诉人", False), ("被申请人", False)):
        m = re.search(rf"^{role}(?:（[^）]*）)?[：:]?\s*([^\n。；;]+)", head, re.M)
        if not m:
            continue
        val = _clean_party(m.group(1))
        if not val:
            continue
        if is_p and not plaintiff:
            plaintiff = val
        elif not is_p and not defendant:
            defendant = val
    return plaintiff, defendant


def _clean_party(s: str) -> str:
    return re.sub(r"[\s　]+", "", s).strip()


def _extract_legal_basis(text: str) -> str:
    """The statute-applied sentence(s): '依照《…》…之规定，判决如下' / '根据《…》…的规定'."""
    m = re.search(
        r"(?:依照|依据|根据)\s*[《][^。]{2,300}?[》][^。]{0,200}?(?:之规定|的规定)",
        text,
    )
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def _extract_decision_result(text: str) -> str:
    """First sentence after 判决如下/裁定如下, else a trailing 驳回上诉，维持原判."""
    m = re.search(r"(?:判决|裁定)\s*如下[：:]?\s*([^\n。]{2,200})", text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    # 终审判决常以「驳回上诉，维持原判。」收尾
    m = re.search(r"(驳回上诉，维持原判|驳回上诉，维持原裁定|撤销[^。]{0,40}?发回重审)", text)
    if m:
        return m.group(1)
    return ""


def _extract_reasoning(text: str) -> str:
    """The court's reasoning narrative (本院认为 … 依照/判决)."""
    m = re.search(r"本院认为[，,：:]?\s*(.{40,2000}?)(?=依照|根据《|判决如下|裁定如下|本判决为|$)", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_points(text: str) -> str:
    """Best-effort 争议焦点 / 裁判要点."""
    m = re.search(r"(?:本案的争议焦点|本案争议焦点)[是为在：:]?\s*([^\n。]{4,200})", text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_panel(text: str) -> str:
    parts = []
    for label in ("审判长", "审判员", "人民陪审员"):
        for m in re.finditer(rf"{label}[：:]\s*([^\n。；;]+)", text):
            val = m.group(1).strip()
            if val:
                parts.append(f"{label}：{val}")
    return "；".join(dict.fromkeys(parts))


def _extract_claims(text: str) -> str:
    """Best-effort capture of the claims at issue."""
    m = re.search(r"权利要求书[^：:\n]*[：:]\s*\n?(.{20,1500}?)(?=\n\s*(?:专利|本|上述|\d+[,、，]|权利要求|\Z))", text, re.S)
    if not m:
        # 判决正文常出现「权利要求1为：“…”」
        m = re.search(r"权利要求1[为是]?[：:]\s*[“\"](.{30,1200}?)[”\"]", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _clean_full_text(text: str) -> str:
    text = re.sub(r"[#*|^{}]+", "", text)
    text = re.sub(r"[ \t]*\|[ \t]*", " ", text)
    text = re.sub(_HORIZONTAL_RULE_RE, "", text)
    text = re.sub(r"---", "", text)
    text = re.sub(r"[\u3000\s]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _case_number_from_filename(name: str) -> str:
    """Derive a case number from the filename when it looks like one."""
    if not name:
        return ""
    m = re.search(r"[\u3000\s]*(\(?[（(]?\d{4}[）)]?[^\s\u3000]{2,40}?号)", name)
    if m:
        return _normalize_case_number(m.group(1))
    return ""


def parse_judgment_markdown(path) -> PatentJudgment:
    """Parse one judgment Markdown file into a PatentJudgment."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    # 去掉 Obsidian 导出时的首行占位符 (U+FFFC)
    text = text.replace("\ufeff", "").replace("\ufffc", "")

    j = PatentJudgment()
    j.source_path = str(path)
    j.source_file = path.stem
    j.file_name = path.name

    meta = _extract_header_meta(text)
    for k, v in meta.items():
        setattr(j, k, v)

    j.case_type = _detect_case_type(text, j.cause)
    if not j.case_number:
        j.case_number = _case_number_from_filename(j.source_file)

    j.legal_basis = _extract_legal_basis(text)
    j.decision_result = _extract_decision_result(text)
    j.legal_reasoning = _extract_reasoning(text)
    j.decision_points = _extract_points(text)
    j.invention_name = _extract_invention_name(text)
    j.patent_holder = _extract_patent_holder(text)
    j.plaintiff, j.defendant = _extract_parties(text)
    j.application_number, j.patent_numbers = _extract_patent_numbers(text)
    j.panel = _extract_panel(text)
    j.claims = _extract_claims(text)
    j.full_text = _clean_full_text(text)
    j.judgment_id = j.case_number or j.source_file
    j.confidence = "parsed"
    return j


def resolve_judgment_id(j: PatentJudgment) -> str:
    """The non-empty node identifier used for SHACL / Neo4j keying."""
    return j.case_number or j.judgment_id or j.source_file


def merge_part_judgments(judgments: List[PatentJudgment]) -> List[PatentJudgment]:
    """Dedupe multi-file judgments (same normalized case_number)."""
    groups: Dict[str, List[PatentJudgment]] = {}
    for j in judgments:
        key = j.case_number or ("__file__", j.source_file)
        groups.setdefault(key, []).append(j)

    out: List[PatentJudgment] = []
    for key, group in groups.items():
        if len(group) == 1:
            out.append(group[0])
            continue
        base = group[0]
        longest = max(group, key=lambda d: len(d.full_text))
        base.full_text = longest.full_text
        for d in group:
            for fname in (
                "decision_date", "court", "invention_name", "patent_holder",
                "plaintiff", "defendant", "panel", "legal_basis",
                "decision_points", "decision_result", "application_number",
            ):
                if not getattr(base, fname) and getattr(d, fname):
                    setattr(base, fname, getattr(d, fname))
        base.patent_numbers = list(dict.fromkeys(
            [p for p in (base.patent_numbers + [pn for d in group for pn in d.patent_numbers])]
        ))
        out.append(base)
    return out


def scan_judgment_corpus(roots, limit=None, __file_filter="*.md"):
    """Parse every judgment Markdown across one or more dirs."""
    if isinstance(roots, (str, Path)):
        roots = [roots]
    results: List[PatentJudgment] = []
    errors: List[str] = []
    files = []
    for r in roots:
        files.extend(sorted(Path(r).glob(__file_filter)))
    for i, f in enumerate(files):
        if limit is not None and i >= limit:
            break
        try:
            results.append(parse_judgment_markdown(f))
        except Exception as e:  # noqa: BLE001 - report, don't hide
            errors.append(f"{f.name}: {e}")
    merged = merge_part_judgments(results)
    return merged, results, errors


def main(argv=None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Parse patent / IP court judgments.")
    parser.add_argument("--root", nargs="+", default=[
        "/Users/xujian/projects/宝宸知识库_Raw/专利判决",
        "/Users/xujian/projects/宝宸知识库_Raw/指导性专利判决文书_md",
    ], help="One or more corpus dirs.")
    parser.add_argument("--limit", type=int, default=None, help="Only parse the first N files (smoke).")
    parser.add_argument("--json", action="store_true", help="Emit parsed records as JSON.")
    args = parser.parse_args(argv)

    from collections import Counter

    merged, results, errors = scan_judgment_corpus(args.root, args.limit)
    stats = {
        "parsed": len(results),
        "errors": len(errors),
        "merged": len(merged),
        "case_type": dict(Counter(d.case_type for d in merged)),
        "with_patent": sum(1 for d in merged if d.patent_numbers),
        "with_case_no": sum(1 for d in merged if d.case_number),
        "with_date": sum(1 for d in merged if d.decision_date),
    }
    print(json.dumps(stats, ensure_ascii=False))
    if errors:
        print("sample_errors:", errors[:5])
    if args.json:
        for d in merged:
            print(json.dumps(d.__dict__, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

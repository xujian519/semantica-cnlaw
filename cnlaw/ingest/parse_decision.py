"""Parse Chinese patent invalidation / reexamination decision Markdown files.

The 无效复审决定 corpus stores each administrative decision as a Markdown file
with heterogeneous naming (patent number, case number ``4W/5W/6W``, ``WX``, a
``+``-joined compound, ``_N`` multi-part suffixes) and three body layouts:

  * A-table-header (``WX*``/``4W*``/``5W*``): a single clean ``|key|value|``
    table at the top.
  * B-patent-number (pure-digit names, ``008073341.md``): a ``# 专利无效复审决定 <id>``
    title, a noisy header table, and a clean ``## 附件表格 3`` / ``## 决定详情``
    key:value table.
  * C-2025-YAML (``决定*``): YAML frontmatter.

The decision type (无效 vs 复审) and every field are derived from the document
text, never from the filename. Extraction is pure (no database) so it is
unit-testable. Per the confirmed 'md-first, JSON-backfill' policy, an optional
JSON sidecar (``knowledge_base/json``) backfills fields the Markdown parse may
miss and flags the record's ``confidence``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# 决定书正文中的关键分隔标记
_SENTINELS = ("<!-- INFO END -->",)
_OBSIDIAN = ("bookCollapseSection",)
_HORIZONTAL_RULE_RE = re.compile(r"^\s*[-*]{3,}\s*$", re.M)
_TMPL_PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}")
# 标题行 (B 格式): # 专利无效复审决定 <id>
_TITLE_RE = re.compile(r"^#\s+专利无效复审决定\s+(\S+)")

# case type: 只能从正文判定。刻意排除裸 "复审决定书"——它在无效文书正文里也会出现，
# 会造成误判；改按「首次出现的文档类型短语位置」裁决。
_REEXAM_MARKERS = ("复审请求审查决定书", "复审请求审查决定", "复 审 决 定 书")
_INVALID_MARKERS = ("无效宣告请求审查决定书", "无效宣告请求审查决定")

# 字段别名表: 规范化后的label -> PatentDecision 字段名
_LABEL_FIELD = {
    "决定号": "decision_id",
    "决定日": "decision_date",
    "发明创造名称": "invention_name",
    "国际分类号": "ipc",
    "国际分类": "ipc",
    "无效宣告请求人": "requesting_party",
    "无效请求人": "requesting_party",
    "第一请求人": "requesting_party",
    "复审请求人": "requesting_party",
    "请求人": "requesting_party",
    "专利权人": "patent_holder",
    "专利号": "application_number",
    "申请号或专利号": "application_number",
    "申请号": "application_number",
    "申请日": "application_date",
    "优先权日": "priority_date",
    "授权公告日": "grant_date",
    "公开日": "publication_date",
    "无效宣告请求日": "requester_date",
    "复审请求日": "requester_date",
    "请求日": "requester_date",
    "合议组组长": "panel",
    "主审员": "panel",
    "参审员": "panel",
    "合议组": "panel",
    "法律依据": "legal_basis",
    "决定要点": "decision_points",
    "案件编号": "case_number",
}

_DATE_FIELDS = {
    "decision_date",
    "application_date",
    "priority_date",
    "publication_date",
    "grant_date",
    "requester_date",
}

_CN_DIGITS = "零一二三四五六七八九"
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


@dataclass
class PatentDecision:
    """A single parsed invalidation / reexamination decision."""

    decision_id: str = ""
    case_type: str = ""  # 复审/无效/待核验
    case_number: str = ""
    decision_date: str = ""
    invention_name: str = ""
    ipc: str = ""
    patent_holder: str = ""
    requesting_party: str = ""
    application_number: str = ""  # 专利号/申请号
    application_date: str = ""
    priority_date: str = ""
    publication_date: str = ""
    grant_date: str = ""
    requester_date: str = ""
    panel: str = ""
    legal_basis: str = ""
    decision_points: str = ""
    decision_result: str = ""  # 结论
    tech_field: str = ""
    domain: str = "专利复审无效"
    source_path: str = ""
    source_file: str = ""
    file_name: str = ""
    full_text: str = ""
    claims_original: str = ""
    evidence: str = ""
    legal_reasoning: str = ""
    confidence: str = ""  # "" / "parsed" / "json_backfilled"


def cn2int(s: str) -> Optional[int]:
    """Convert a Chinese numeral (例如 '二百九十四') to an int, or None."""
    if not s or not s.strip():
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    if all(ch in _CN_DIGITS for ch in s):
        if len(s) == 1:
            v = _CN_DIGITS.index(s)
            return v if v > 0 else None
        return None
    total = current = 0
    for ch in s:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS.index(ch)
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            total += (current if current else 1) * unit
            current = 0
        else:
            return None
    val = total + current
    return val if val > 0 else None


def _clean(text: str) -> str:
    """Collapse whitespace and strip bold markers from a value."""
    return re.sub(r"\s+", "", text or "").strip()


def _norm_label(label: str) -> str:
    """Normalize a table label for matching against _LABEL_FIELD."""
    return re.sub(r"[\s：:·、，,;；]", "", label or "")


def _normalize_date(s: Optional[str]) -> str:
    """Normalize a (possibly noisy) Chinese date to ISO YYYY-MM-DD, or ''."""
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    patterns = [
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", 3),
        (r"(\d{4})年(\d{1,2})月", 2),
        (r"(\d{4})\.(\d{2})\.(\d{2})", 3),
        (r"(\d{4})-(\d{2})-(\d{2})", 3),
    ]
    for pat, nd in patterns:
        m = re.search(pat, s)
        if not m:
            continue
        y = int(m.group(1))
        mo = int(m.group(2))
        d = int(m.group(3)) if nd == 3 else 1
        if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def register(meta: Dict[str, str], field: str, value: Optional[str]) -> None:
    """Write a field if it is non-empty and (for dates/ipc) valid.

    This lets a noisy header be skipped in favour of the cleaner attachment
    table later in the document (first-non-empty for strings, but only a
    *valid* date / IPC code is ever written for those fields).
    """
    value = (value or "").strip()
    if not value:
        return
    if field in _DATE_FIELDS:
        iso = _normalize_date(value)
        if iso:
            meta[field] = iso
        return
    if field == "ipc":
        if re.search(r"[A-H]\d", value):
            meta.setdefault(field, value)
        return
    if field == "decision_id":
        m = re.search(r"第\s*(\d+)\s*号", value)
        if m:
            meta.setdefault(field, m.group(1))
        return
    if field == "case_number":
        v = re.sub(r"^第|[号：:\s]+$", "", value)
        meta.setdefault(field, v)
        return
    meta.setdefault(field, value)


def _extract_table_meta(text: str) -> Dict[str, str]:
    """Pull key:value metadata from table lines (inline label：value + |k|v|)."""
    meta: Dict[str, str] = {}
    for line in text.split("\n"):
        if "|" not in line:
            continue
        # inline label：value inside a table cell, e.g. 申请号或专利号：00807334.1
        for m in re.finditer(r"([\u4e00-\u9fff]{2,12}?)\s*[：:]\s*([^|]+?)(?=\||\s*$)", line):
            label = _norm_label(m.group(1))
            if label in _LABEL_FIELD:
                register(meta, _LABEL_FIELD[label], m.group(2))
        # 2-cell | label | value | pairs (attachment table 3 / A-format table)
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        for i in range(len(cells) - 1):
            label = _norm_label(cells[i])
            if label not in _LABEL_FIELD:
                continue
            # duplicate-column artifact: the "value" is itself another field label
            # (e.g. '发明创造名称： | 发明创造名称： | 将管道…'), skip it.
            if _norm_label(cells[i + 1]) in _LABEL_FIELD:
                continue
            register(meta, _LABEL_FIELD[label], cells[i + 1])
    return meta


def _extract_compact_meta(text: str, meta: Dict[str, str]) -> None:
    """Handle #key=value and YAML frontmatter metadata forms."""
    for m in re.finditer(r"^#(\S+?)\s*=\s*(.*)$", text, re.M):
        label = _norm_label(m.group(1))
        if label in _LABEL_FIELD:
            register(meta, _LABEL_FIELD[label], m.group(2))
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            for line in text[3:end].split("\n"):
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                label = _norm_label(key)
                val = val.strip().strip('"').strip("'")
                if label in _LABEL_FIELD:
                    register(meta, _LABEL_FIELD[label], val)
                elif key.strip() == "decision_type":
                    dt = val
                    if "全部" in dt:
                        meta["decision_result"] = "宣告专利权全部无效"
                    elif "部分" in dt:
                        meta["decision_result"] = "宣告专利权部分无效"
                    elif "有效" in dt:
                        meta["decision_result"] = "维持专利权有效"
                    elif "撤销" in dt:
                        meta["decision_result"] = "撤销驳回决定"
                    elif "维持" in dt:
                        meta["decision_result"] = "维持驳回决定"


def _extract_global_ids(text: str, meta: Dict[str, str]) -> None:
    """Fallback: decision number and case number from the front matter.

    The B (patent-number) layout prints the decision number inline as
    '（第566693号）' and the case number as '第4W116319号'; neither is a
    labeled table row, so we fill them from the document text if missing.
    """
    head = text[:4000]
    if not meta.get("decision_id"):
        m = re.search(r"（第\s*(\d+)\s*号）", head)
        if m:
            meta["decision_id"] = m.group(1)
    if not meta.get("case_number"):
        m = re.search(r"第\s*(\d+[A-Z][0-9]+)\s*号", head)
        if m:
            meta["case_number"] = m.group(1)


def _case_number_from_filename(name: str) -> str:
    """Derive a case number from a filename only when it looks like one.

    Case-like names: WX13261.md, 1F101201_....md, 4W00493+....md, 5W/6W names.
    Plain patent-number names such as 008073341.md are NOT case numbers and are
    left empty.
    """
    name = name or ""
    for pat in (r"^(WX\d+)", r"^(1F\d+)", r"^([0-9]*[456]W\d+)", r"^([0-9]*[456]W\d+)\+"):
        m = re.match(pat, name)
        if m:
            return m.group(1)
    return ""


def _detect_case_type(text: str) -> str:
    """Determine 复审/无效 from specific body phrases (never the filename).

    The document-type phrase sits near the top, so the type whose marker appears
    first wins. This avoids misclassifying an invalidation decision that happens
    to mention a reexamination decision elsewhere in its body.
    """
    head = text[:4000]

    def _first(markers: List[str]) -> int:
        idxs = [head.find(m) for m in markers]
        idxs = [i for i in idxs if i != -1]
        return min(idxs) if idxs else -1

    ri = _first(list(_REEXAM_MARKERS))
    ii = _first(list(_INVALID_MARKERS))
    if ri == -1 and ii == -1:
        return "待核验"
    if ri == -1:
        return "无效"
    if ii == -1:
        return "复审"
    return "复审" if ri < ii else "无效"


def _find_section(text: str, starts: List[str], ends: List[str]) -> str:
    """Return the text between the first start-marker and the first end-marker."""
    start_idx = -1
    start_len = 0
    for s in starts:
        idx = text.find(s)
        if idx != -1:
            start_idx = idx
            start_len = len(s)
            break
    if start_idx == -1:
        return ""
    content_start = start_idx + start_len
    end_idxs = [text.find(e, content_start) for e in ends]
    end_idxs = [i for i in end_idxs if i != -1]
    end_idx = min(end_idxs) if end_idxs else len(text)
    return text[content_start:end_idx].strip()


def _extract_decision_result(text: str, case_type: str) -> str:
    """Extract the outcome from the '三、决定' section."""
    section = _find_section(
        text,
        starts=["三、决定", "三．决定", "三、 决定", "三.决定"],
        ends=["当事人对本决定不服", "根据专利法第46条第2款", "根据专利法第41条第2款",
              "如对本复审请求审查决定不服", "如对本复审请求审查决定不服"],
    )
    if case_type == "复审":
        if "撤销" in section or re.search(r"撤销国家知识产权局", text[:6000]):
            return "撤销驳回决定"
        if section and ("维持" in section and "驳回" in section):
            return "维持驳回决定"
        return "待核验"
    if section:
        if "部分无效" in section:
            return "宣告专利权部分无效"
        if re.search(r"宣告[^。\n]{0,80}?无效", section):
            return "宣告专利权全部无效"
        if re.search(r"维持[^。\n]{0,120}?有效", section):
            return "维持专利权有效"
    # 复审 中 撤销 在「三、决定」区段; 无效复审正文末尾的「维持…有效」兜底
    if re.search(r"维持[^。\n]{0,120}?有效", text[-1500:]):
        return "维持专利权有效"
    return "待核验"


def _extract_section_between(text: str, markers: List[str]) -> str:
    """Return first marker's tail, or ''."""
    for m in markers:
        idx = text.find(m)
        if idx != -1:
            return text[idx + len(m):]
    return ""


def _extract_claims(text: str) -> str:
    """Best-effort: capture the claims after 权利要求书如下：."""
    m = re.search(
        r"(?:授权公告时的权利要求书|公告的权利要求书|权利要求书)[^：:\n]*[：:]\s*\n?(.*?)(?=\n\s*(?:请求人|经形式审查|针对|根据国家知识产权局|二[、．]|一、案由|\$))",
        text,
        re.S,
    )
    return re.sub(r"\s+", " ", (m.group(1) if m else "")).strip()


def _extract_evidence(text: str) -> str:
    """Best-effort: capture the evidence list in the 案由 section."""
    case_section = _find_section(text, starts=["一、案由", "一．案由", "一、 案由"], ends=["二、", "二．"])
    if not case_section:
        case_section = text[:8000]
    m = re.search(
        r"提交了如下证据[：:]\s*\n?(.*?)(?=\n\s*(?:经形式审查|专利权人|口头审理|至此|二[、．]|请求人认为|请求人于|\Z))",
        case_section,
        re.S,
    )
    if not m:
        m = re.search(r"其提交的证据为[：:]\s*\n?(.*?)(?=\n\s*(?:经形式审查|合议组|二[、．]|\Z))", case_section, re.S)
    return re.sub(r"\s+", " ", (m.group(1) if m else "")).strip()


def _extract_reasoning(text: str) -> str:
    """Best-effort: the '二、决定的理由' narrative as a summary string."""
    section = _find_section(
        text,
        starts=["二、决定的理由", "二．决定的理由"],
        ends=["三、决定", "三．决定", "三、 决定"],
    )
    return re.sub(r"\s+", " ", section).strip()


def _clean_full_text(text: str) -> str:
    """Produce a lower-noise decision text for document-level embedding."""
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"\*\*", "", text)
    text = re.sub(_HORIZONTAL_RULE_RE, "", text)
    text = re.sub(r"[ \t]*\|[ \t]*", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_decision_markdown(path, json_record: Optional[Dict] = None) -> PatentDecision:
    """Parse one decision Markdown file into a PatentDecision.

    Args:
        path: Path to the .md file (str or Path).
        json_record: Optional parsed record from knowledge_base/json used to
            backfill missing fields.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    text0 = text
    # strip Obsidian markers / sentinel (no-op for these files, kept for parity)
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)

    dec = PatentDecision()
    dec.source_path = str(path)
    dec.source_file = path.stem
    dec.file_name = path.name
    dec.case_type = _detect_case_type(text)
    dec.full_text = _clean_full_text(text)

    meta = _extract_table_meta(text)
    _extract_compact_meta(text, meta)
    _extract_global_ids(text, meta)

    for k, v in meta.items():
        setattr(dec, k, v)

    if not dec.case_number:
        dec.case_number = _case_number_from_filename(dec.source_file)

    dec.decision_result = _extract_decision_result(text, dec.case_type)
    dec.claims_original = _extract_claims(text)
    dec.evidence = _extract_evidence(text)
    dec.legal_reasoning = _extract_reasoning(text)

    if json_record:
        _backfill_from_json(dec, json_record)

    dec.confidence = "json_backfilled" if dec.confidence == "json_backfilled" else "parsed"
    return dec


def _backfill_from_json(dec: PatentDecision, record: Dict) -> None:
    """Fill empty fields from the pre-extracted JSON sidecar record.

    Only empty fields are filled; mismatched non-empty fields are left as-is and
    not flagged (they are tracked as 'parsed' plus the diff is disjoint).
    """
    meta = record.get("metadata") or {}
    mapping = {
        "decision_no": "decision_id",
        "decision_date": "decision_date",
        "invention_name": "invention_name",
        "ipc": "ipc",
        "patent_holder": "patent_holder",
        "requesting_party": "requesting_party",
        "application_number": "application_number",
        "application_date": "application_date",
        "grant_date": "grant_date",
        "decision_points": "decision_points",
        "case_number": "case_number",
    }
    filled = False
    for src, dst in mapping.items():
        val = meta.get(src)
        if val and not getattr(dec, dst):
            setattr(dec, dst, val)
            filled = True
    lb = meta.get("legal_basis")
    if lb and not dec.legal_basis:
        dec.legal_basis = "，".join(lb) if isinstance(lb, list) else str(lb)
        filled = True
    if not dec.decision_result:
        dr = record.get("decision_result") or meta.get("decision_result")
        if dr:
            dec.decision_result = dr
            filled = True
    if not dec.claims_original and record.get("claims_original"):
        dec.claims_original = record["claims_original"]
        filled = True
    if filled:
        dec.confidence = "json_backfilled"


def merge_multipart(decisions: List[PatentDecision]) -> List[PatentDecision]:
    """Merge files that belong to the same case (multi-part '_N', duplicates).

    Group key is (case_number, decision_id); a case with no case_number falls
    back to its decision_id. Across a group the longest full_text and the
    concatenated claims are kept, and empty fields are filled from siblings.
    """
    groups: Dict[tuple, List[PatentDecision]] = {}
    for d in decisions:
        key = (d.case_number or "", d.decision_id or "")
        if key == ("", ""):
            # fall back to source_file so no unrelated documents merge
            key = ("__file__", d.source_file)
        groups.setdefault(key, []).append(d)

    out: List[PatentDecision] = []
    for group in groups.values():
        if len(group) == 1:
            out.append(group[0])
            continue
        base = group[0]
        longest = max(group, key=lambda d: len(d.full_text))
        claims_parts = [d.claims_original for d in group if d.claims_original]
        base.full_text = longest.full_text
        if claims_parts:
            base.claims_original = "\n".join(dict.fromkeys(claims_parts))
        for d in group:
            for fname in (
                "decision_date", "invention_name", "ipc", "patent_holder",
                "requesting_party", "application_number", "grant_date",
                "panel", "legal_basis", "decision_points", "decision_result",
            ):
                if not getattr(base, fname) and getattr(d, fname):
                    setattr(base, fname, getattr(d, fname))
        out.append(base)
    return out


def scan_parse_corpus(root: str, limit: Optional[int] = None):
    """Parse every decision Markdown in a directory (optionally capped)."""
    root = Path(root)
    results: List[PatentDecision] = []
    errors: List[str] = []
    for i, f in enumerate(sorted(root.glob("*.md"))):
        if limit is not None and i >= limit:
            break
        try:
            results.append(parse_decision_markdown(f))
        except Exception as e:  # noqa: BLE001 - report, don't hide
            errors.append(f"{f.name}: {e}")
    return results, errors


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Parse patent invalidation / reexamination decisions.")
    parser.add_argument("--root", default="/Users/xujian/projects/宝宸知识库_Raw/无效复审决定")
    parser.add_argument("--limit", type=int, default=None, help="Only parse the first N files (smoke).")
    parser.add_argument("--json-dir", default=None,
                        help="knowledge_base/json sidecar dir used to backfill/validate fields.")
    args = parser.parse_args(argv)

    import json as _json
    from collections import Counter

    json_index: Dict[str, Dict] = {}
    if args.json_dir:
        jdir = Path(args.json_dir)
        for jf in jdir.glob("*.json"):
            try:
                rec = _json.loads(jf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            json_index.setdefault(rec.get("source_file", jf.stem), rec)

    def _with_backfill(path: Path):
        rec = json_index.get(path.stem) or json_index.get(path.name)
        return parse_decision_markdown(path, rec)

    results: List[PatentDecision] = []
    errors: List[str] = []
    root = Path(args.root)
    for i, f in enumerate(sorted(root.glob("*.md"))):
        if args.limit is not None and i >= args.limit:
            break
        try:
            results.append(_with_backfill(f))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {e}")

    types = Counter(d.case_type for d in results)
    res = Counter(d.decision_result for d in results)
    backfilled = Counter(d.confidence for d in results)
    merged = merge_multipart(results)
    print(
        {
            "parsed": len(results),
            "errors": len(errors),
            "case_type": dict(types),
            "decision_result": dict(res),
            "confidence": dict(backfilled),
            "merged": len(merged),
            "json_sidecar": len(json_index),
        }
    )
    if errors:
        print("sample_errors:", errors[:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

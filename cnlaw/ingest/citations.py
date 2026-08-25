"""Extract and resolve article-to-article citations (Layer 3 remaining).

Chinese statutes refer to other articles inline with two patterns:

  - same-document: "本法第X条" / "本条例第X条" / "本细则第X条" / "本办法第X条"
  - cross-document: "《某法》第X条"

This module extracts those references as plain data and resolves each to a
concrete source->target article pair that is materialized as a ``:cites`` edge
in Neo4j. The reference handling is pure (no database) so it is unit-testable;
the ``apply_citations`` step persists the edges.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

_SAME_DOC_RE = re.compile(
    r"本(?:法|条例|细则|办法|规定|决定)[第]?([一二三四五六七八九十百千零〇0-9]{1,6})条"
)
_CROSS_DOC_RE = re.compile(r"《([^》]{1,50})》\s*第([一二三四五六七八九十百千零〇0-9]{1,6})条")
_NUM_RE = re.compile(r"第([一二三四五六七八九十百千零〇0-9]{1,6})条")

# The guideline cites statutes by their bare name (专利法/专利法实施细则), not
# wrapped in 《》. A name is a CJK string ending in 法 (optionally 实施细则).
_BARE_LAW_RE = re.compile(
    r"([\u4e00-\u9fff]{2,12}?法(?:实施细则)?)\s*第([一二三四五六七八九十百千零〇0-9]{1,6})条"
)
# Leading connective words must not be swallowed into a bare law name, so the
# matched name is split on them and only the final noun kept.
_BARE_PREFIX_SPLIT = re.compile(
    r"(?:依照|根据|适用|参见|参照|按照|依据|按|如|而|对于|关于|所述|前述|应当|违反|属于|该|本|指)"
)
# The guideline also cross-references its own sections: 本章第 N.M 节 (same doc)
# and 本部分第X章第 N.M 节 (a sibling chapter in the same 部分).
_GUIDE_CH_RE = re.compile(r"本章\s*第\s*([0-9]+(?:\.[0-9]+)*)\s*节")
_GUIDE_PART_RE = re.compile(
    r"本部分\s*第([一二三四五六七八九十]+)章\s*第\s*([0-9]+(?:\.[0-9]+)*)\s*节"
)

_CN_DIGITS = "零一二三四五六七八九"
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}

# Article node id, matching vectorize.make_id so edges align with the FAISS/sidecar keys.
KEY_TMPL = "{full_name}@{source_date}~{number}"


class Citation(NamedTuple):
    """A single referenced article inside a source article's text.

    ``kind`` is ``'same'`` (references "本法第X条" within its own document) or
    ``'cross'`` (references "《某法》第X条" in another document). ``number`` is
    the referenced article's order number as a plain integer.
    """

    kind: str
    name: str
    number: int


def cn2int(s: str) -> Optional[int]:
    """Convert a Chinese numeral (例如 '二百九十四') to an int, or None if invalid."""
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
    total = 0
    current = 0
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


def number_int(number: str) -> Optional[int]:
    """Extract the article order number from a stored number like '第一百二十五条'."""
    m = _NUM_RE.search(number or "")
    return cn2int(m.group(1)) if m else None


def extract_citations(text: str, self_name: str) -> List[Citation]:
    """Pull same-document, cross-document, and guide-section references.

    ``number`` is an int for statute references (第X条) and a dotted section path
    string (e.g. ``2.1``) for guideline section references. ``guide_chapter`` and
    ``guide_part`` kinds carry, respectively, the same-document section reference
    and the target chapter ordinal (报 e.g. ``"四"``) for a sibling-chapter one.
    """
    out: List[Citation] = []
    for name, num in _CROSS_DOC_RE.findall(text or ""):
        n = cn2int(num)
        if n:
            out.append(Citation("cross", name, n))
    # bare statute name (no 《》): 专利法第X条 / 专利法实施细则第X条
    for name, num in _BARE_LAW_RE.findall(text or ""):
        n = cn2int(num)
        name = _BARE_PREFIX_SPLIT.split(name)[-1].strip()
        if n and name:
            out.append(Citation("cross", name, n))
    for num in _SAME_DOC_RE.findall(text or ""):
        n = cn2int(num)
        if n:
            out.append(Citation("same", self_name, n))
    for sec in _GUIDE_CH_RE.findall(text or ""):
        out.append(Citation("guide_chapter", self_name, sec))
    for ch, sec in _GUIDE_PART_RE.findall(text or ""):
        out.append(Citation("guide_part", ch, sec))
    return out


def build_doc_index(articles: Iterable[Dict]) -> Dict[str, Dict[str, str]]:
    """Map ``full_name -> {source_date: status}`` for version/name resolution."""
    idx: Dict[str, Dict[str, str]] = {}
    for a in articles:
        fn = a["full_name"]
        sd = a.get("source_date") or ""
        idx.setdefault(fn, {})[sd] = a.get("status", "")
    return idx


def build_article_index(articles: Iterable[Dict]) -> Dict[Tuple[str, str, int], str]:
    """Map ``(full_name, source_date, number_int) -> number_text`` so a citation
    can be resolved back to a concrete article key."""
    idx: Dict[Tuple[str, str, int], str] = {}
    for a in articles:
        n = number_int(a["number"])
        if n is not None:
            idx[(a["full_name"], a.get("source_date") or "", n)] = a["number"]
    return idx


def resolve_name(name: str, doc_index: Dict[str, Dict[str, str]]) -> Optional[str]:
    """Match a possibly-abbreviated citation name to a stored full_name.

    Prefers an exact match, then a unique substring match (citation name is a
    substring of a full_name, e.g. '土地管理法' -> '中华人民共和国土地管理法'),
    then the reverse. Ambiguous matches return None.
    """
    if name in doc_index:
        return name
    contained = [fn for fn in doc_index if name in fn]
    if len(contained) == 1:
        return contained[0]
    if len(contained) > 1:
        return None
    reverse = [fn for fn in doc_index if fn in name]
    return reverse[0] if len(reverse) == 1 else None


def _part_chapter_of(full_name: str) -> Optional[Tuple[str, str]]:
    """Extract the (部分, 章) ordinal pair from a guideline full_name.

    A guideline full_name looks like ``专利审查指南 第二部分 实质审查·第四章 创造性``;
    this returns ``("二", "四")``, or None for a non-guideline name.
    """
    pm = re.search(r"第([一二三四五六七八九十]+)部分", full_name or "")
    cm = re.search(r"第([一二三四五六七八九十]+)章", full_name or "")
    return (pm.group(1), cm.group(1)) if (pm and cm) else None


def build_part_chapter_index(articles: Iterable[Dict]) -> Dict[Tuple[str, str], str]:
    """Map ``(部分, 章) -> full_name`` for sibling-chapter resolution.

    A duplicate (部分, 章) pair (two documents claiming the same slot) is dropped
    so a reference never resolves ambiguously.
    """
    idx: Dict[Tuple[str, str], Optional[str]] = {}
    for fn in {a["full_name"] for a in articles}:
        pc = _part_chapter_of(fn)
        if pc is None:
            continue
        idx[pc] = None if pc in idx else fn
    return {k: v for k, v in idx.items() if v is not None}


def build_core_alias(articles: Iterable[Dict]) -> Dict[str, str]:
    """Map a document's bare core name -> full_name for citations that drop the
    state prefix (e.g. 专利法 -> 中华人民共和国专利法). Conflicts are dropped."""
    alias: Dict[str, Optional[str]] = {}
    for fn in {a["full_name"] for a in articles}:
        core = re.sub(r"^中华人民共和国", "", fn)
        alias[core] = None if core in alias else fn
    return {k: v for k, v in alias.items() if v is not None}


def _resolve_bare(
    name: str, doc_index: Dict[str, Dict[str, str]], core_alias: Dict[str, str]
) -> Optional[str]:
    """Resolve a possibly-bare statute name to a stored full_name.

    ``专利法实施细则`` resolves on its own (unique substring), while ``专利法``
    is a substring of both 专利法 and 专利法实施细则 so it needs the core alias.
    """
    resolved = resolve_name(name, doc_index)
    if resolved:
        return resolved
    return core_alias.get(name)


def pick_doc_version(full_name: str, doc_index: Dict[str, Dict[str, str]]) -> Optional[str]:
    """Choose the source_date of the current ('现行有效') version, else the newest.

    An undated version is treated as current, so if the only current version has
    an empty source_date it is returned.
    """
    versions = doc_index.get(full_name)
    if not versions:
        return None
    current = [sd for sd, st in versions.items() if st == "现行有效"]
    if current:
        dated = sorted((sd for sd in current if sd), reverse=True)
        return dated[0] if dated else current[0]
    dated = sorted((sd for sd in versions if sd), reverse=True)
    return dated[0] if dated else next(iter(versions))


def _article_key(full_name: str, source_date: str, number: str) -> str:
    return KEY_TMPL.format(full_name=full_name, source_date=source_date or "", number=number)


def build_citation_plan(
    articles: Iterable[Dict],
) -> List[Tuple[Tuple[str, str, str], Tuple[str, str, str]]]:
    """Resolve the referenced articles for every article into ``:cites`` pairs.

    Each returned pair is ``((source full_name, source_date, number),
    (target full_name, target_date, number))`` for every resolvable reference.
    A same-document reference targets the same document version the source
    belongs to; a cross-document reference targets the current version of the
    cited document. References that resolve to nothing, or to an article that is
    not in the corpus, are dropped.
    """
    articles = list(articles)
    doc_index = build_doc_index(articles)
    article_index = build_article_index(articles)
    # section path index for guideline cross-references (number is a dotted path)
    section_index = {
        (a["full_name"], a.get("source_date") or "", a["number"]): a["number"]
        for a in articles
    }
    part_ch_index = build_part_chapter_index(articles)
    core_alias = build_core_alias(articles)
    edges: Set[Tuple[Tuple[str, str, str], Tuple[str, str, str]]] = set()

    for a in articles:
        src_name = a["full_name"]
        src_date = a.get("source_date") or ""
        src_number = a["number"]
        for cit in extract_citations(a.get("text", ""), src_name):
            if cit.kind == "same":
                target = (src_name, src_date, cit.number)
                tgt_number = article_index.get(target)
                if tgt_number is None:
                    continue
                if (src_name, src_date, tgt_number) == (src_name, src_date, src_number):
                    continue  # drop self-references
                edges.add(
                    ((src_name, src_date, src_number), (src_name, src_date, tgt_number))
                )
            elif cit.kind == "cross":
                resolved = _resolve_bare(cit.name, doc_index, core_alias)
                if resolved is None:
                    continue
                tdate = pick_doc_version(resolved, doc_index)
                if tdate is None:
                    continue
                target = (resolved, tdate, cit.number)
                tgt_number = article_index.get(target)
                if tgt_number is None:
                    continue
                if (resolved, tdate, tgt_number) == (src_name, src_date, src_number):
                    continue
                edges.add(
                    ((src_name, src_date, src_number), (resolved, tdate, tgt_number))
                )
            elif cit.kind == "guide_chapter":
                # same-document section: 本章第 N.M 节
                if (src_name, src_date, cit.number) in section_index and cit.number != src_number:
                    edges.add(
                        ((src_name, src_date, src_number), (src_name, src_date, cit.number))
                    )
            elif cit.kind == "guide_part":
                # sibling chapter in the same 部分: 本部分第X章第 N.M 节
                src_pc = _part_chapter_of(src_name)
                if src_pc is None:
                    continue
                tgt_fn = part_ch_index.get((src_pc[0], cit.name))
                if tgt_fn is None:
                    continue
                tdate = pick_doc_version(tgt_fn, doc_index)
                if tdate is None:
                    continue
                if (tgt_fn, tdate, cit.number) in section_index:
                    src_key = (src_name, src_date, src_number)
                    tgt_key = (tgt_fn, tdate, cit.number)
                    if src_key != tgt_key:
                        edges.add((src_key, tgt_key))

    return sorted(edges, key=lambda e: (_article_key(*e[0]), _article_key(*e[1])))


def load_articles(store) -> List[Dict]:
    """Pull every Article with its document status for citation resolution."""
    records = store.execute_query(
        "MATCH (d:LegalDocument)-[:has_article]->(a:Article) "
        "RETURN a.full_name AS full_name, a.source_date AS source_date, "
        "a.number AS number, a.text AS text, d.status AS status"
    ).get("records", [])
    return records


def apply_citations(store, articles: Optional[List[Dict]] = None) -> Dict[str, int]:
    """Materialize ``:cites`` edges between Article nodes. Idempotent (MERGE)."""
    if articles is None:
        articles = load_articles(store)
    plan = build_citation_plan(articles)
    rows = [
        {
            "sfn": s[0],
            "ssd": s[1] or "",
            "snum": s[2],
            "tfn": t[0],
            "tsd": t[1] or "",
            "tnum": t[2],
        }
        for s, t in plan
    ]
    if rows:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (a:Article {full_name:r.sfn, source_date:r.ssd, number:r.snum}) "
            "MATCH (b:Article {full_name:r.tfn, source_date:r.tsd, number:r.tnum}) "
            "MERGE (a)-[:cites]->(b)",
            {"rows": rows},
        )
    return {"citations": len(plan), "source_articles": len(articles)}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build the article citation graph (:cites).")
    parser.add_argument("--dry-run", action="store_true", help="Count resolvable citations only.")
    args = parser.parse_args(argv)

    from .load_laws_neo4j import make_store

    store = make_store()
    articles = load_articles(store)
    plan = build_citation_plan(articles)
    if args.dry_run:
        print({"source_articles": len(articles), "citations": len(plan)})
        return 0
    print(apply_citations(store, articles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

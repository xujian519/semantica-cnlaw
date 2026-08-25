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
    """Pull same-document and cross-document article references from ``text``."""
    out: List[Citation] = []
    for name, num in _CROSS_DOC_RE.findall(text or ""):
        n = cn2int(num)
        if n:
            out.append(Citation("cross", name, n))
    for num in _SAME_DOC_RE.findall(text or ""):
        n = cn2int(num)
        if n:
            out.append(Citation("same", self_name, n))
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
    edges: Set[Tuple[Tuple[str, str, str], Tuple[str, str, str]]] = set()

    for a in articles:
        src_n = number_int(a["number"])
        if src_n is None:
            continue
        src_name = a["full_name"]
        src_date = a.get("source_date") or ""
        src_number = a["number"]
        for cit in extract_citations(a.get("text", ""), src_name):
            if cit.kind == "same":
                target = (src_name, src_date, cit.number)
            else:
                resolved = resolve_name(cit.name, doc_index)
                if resolved is None:
                    continue
                tdate = pick_doc_version(resolved, doc_index)
                if tdate is None:
                    continue
                target = (resolved, tdate, cit.number)
            tgt_number = article_index.get(target)
            if tgt_number is None:
                continue
            if (target[0], target[1], tgt_number) == (src_name, src_date, src_number):
                continue  # drop self-references
            edges.add(((src_name, src_date, src_number), (target[0], target[1], tgt_number)))

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

"""Build ``based_on`` edges from patent judgments to the statute Articles they apply.

A judgment cites statute provisions inline (专利法第十一条第一款, 《最高人民法院关于…》第四条…).
This module reuses the citation extraction/resolution helpers from citations.py and emits
``PatentJudgment -[:based_on]-> Article`` pairs so the graph shows which law articles
each judgment applied. Pure (no database); applying the plan is the only step that
touches Neo4j.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .citations import (
    extract_citations,
    load_articles,
    pick_doc_version,
    build_article_index,
    build_core_alias,
    build_doc_index,
    _resolve_bare,
)
from .decision_citations import _clean_ref_name


def extract_statute_refs(text: str) -> List[Tuple[str, int]]:
    """Unique ``(statute name, article int)`` refs in a judgment text."""
    seen = set()
    refs: List[Tuple[str, int]] = []
    for cit in extract_citations(text or "", ""):
        if cit.kind != "cross":
            continue
        name = _clean_ref_name(cit.name)
        if not name:
            continue
        key = (name, cit.number)
        if key in seen:
            continue
        seen.add(key)
        refs.append((name, cit.number))
    return refs


def build_judgment_citation_plan(
    judgments: List, articles: List[Dict]
) -> List[Tuple[str, str, str, str, str]]:
    """Resolve judgment statute refs to concrete Article node keys.

    Each returned tuple is ``(case_number, judgment_id, full_name, source_date,
    number_text)`` where the Article node is keyed in Neo4j by
    ``(full_name, source_date, number)``.
    """
    doc_index = build_doc_index(articles)
    article_index = build_article_index(articles)
    core_alias = build_core_alias(articles)

    edges: List[Tuple[str, str, str, str, str]] = []
    seen = set()
    for j in judgments:
        refs = extract_statute_refs((j.legal_basis or "") + " " + (j.full_text or ""))
        for name, num in refs:
            resolved = _resolve_bare(name, doc_index, core_alias)
            if resolved is None:
                continue
            tdate = pick_doc_version(resolved, doc_index)
            if tdate is None:
                continue
            number_text = article_index.get((resolved, tdate, num))
            if number_text is None:
                continue
            edge = (j.case_number or "", j.judgment_id, resolved, tdate, number_text)
            if edge in seen:
                continue
            seen.add(edge)
            edges.append(edge)
    return edges


def apply_judgment_citations(store, judgments: List | None = None) -> Dict[str, int]:
    """Materialize ``:based_on`` edges between PatentJudgment and Article nodes."""
    if judgments is None:
        from .load_judgments_neo4j import scan_judgments

        judgments, _raw, _errs = scan_judgments()

    articles = load_articles(store)
    plan = build_judgment_citation_plan(judgments, articles)
    rows = [
        {"cn": cn, "jid": jid, "afn": afn, "asd": asd or "", "anum": anum}
        for (cn, jid, afn, asd, anum) in plan
    ]
    if rows:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (j:PatentJudgment {case_number:r.cn, judgment_id:r.jid}) "
            "MATCH (a:Article {full_name:r.afn, source_date:r.asd, number:r.anum}) "
            "MERGE (j)-[:based_on]->(a)",
            {"rows": rows},
        )
    return {"based_on": len(plan), "judgments": len(judgments)}


def main(argv=None) -> int:
    import argparse

    from .load_laws_neo4j import make_store
    from .load_judgments_neo4j import scan_judgments

    parser = argparse.ArgumentParser(description="Build the judgment->statute based_on graph.")
    parser.add_argument("--dry-run", action="store_true", help="Count resolvable based_on edges only.")
    args = parser.parse_args(argv)

    store = make_store()
    judgments, _raw, _errs = scan_judgments()
    articles = load_articles(store)
    plan = build_judgment_citation_plan(judgments, articles)
    if args.dry_run:
        print({"judgments": len(judgments), "based_on": len(plan)})
        return 0
    rows = [
        {"cn": cn, "jid": jid, "afn": afn, "asd": asd or "", "anum": anum}
        for (cn, jid, afn, asd, anum) in plan
    ]
    if rows:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (j:PatentJudgment {case_number:r.cn, judgment_id:r.jid}) "
            "MATCH (a:Article {full_name:r.afn, source_date:r.asd, number:r.anum}) "
            "MERGE (j)-[:based_on]->(a)",
            {"rows": rows},
        )
    print({"judgments": len(judgments), "based_on": len(plan)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

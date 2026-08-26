"""Build ``based_on`` edges from patent decisions to the statute Articles they apply.

A decision cites statute provisions inline (专利法第22条第3款, 专利法实施细则第20条…).
This module reuses the citation extraction/resolution helpers from citations.py and
emits ``PatentDecision -[:based_on]-> Article`` pairs so the graph shows which law
articles each decision applied, and (in reverse) which decisions relied on a given
article. Pure (no database); applying the plan is the only step that touches Neo4j.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .citations import (
    extract_citations,
    load_articles,
    pick_doc_version,
    build_article_index,
    build_core_alias,
    build_doc_index,
    _resolve_bare,
)
from .load_decisions_neo4j import decision_key


# Bare-name extraction grabs preceding clause characters (「、和」「款和」) into the
# name; strip those connectives / clause tails so the name resolves cleanly.
_LEADING_NOISE_RE = re.compile(
    r"^(?:以及|及|和|与|或|款|项|条|目|依照|根据|按照|依据|按|参照|参见|适用|如|而|"
    r"对于|关于|所述|前述|应当|违反|属于|该|本|指|之|即|、|，|,)+"
)


def _clean_ref_name(name: str) -> str:
    return _LEADING_NOISE_RE.sub("", name or "")


def extract_statute_refs(text: str) -> List[Tuple[str, int]]:
    """Unique ``(statute name, article int)`` refs in a decision text.

    Only cross-document references (bare 专利法第X条 / 《某法》第X条) are kept;
    same-document and guide-section kinds do not apply to decisions.
    """
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


def build_decision_citation_plan(
    decisions: List, articles: List[Dict]
) -> List[Tuple[str, str, str, str]]:
    """Resolve decision statute refs to concrete Article node keys.

    Each returned tuple is ``(decision_key, full_name, source_date, number_text)``
    where the Article node is keyed in Neo4j by ``(full_name, source_date, number)``.
    Refs that resolve to a statute / article not present in the corpus are dropped.
    """
    doc_index = build_doc_index(articles)
    article_index = build_article_index(articles)
    core_alias = build_core_alias(articles)

    edges: List[Tuple[str, str, str, str]] = []
    seen = set()
    for d in decisions:
        dkey = decision_key(d.case_number, d.decision_id)
        refs = extract_statute_refs((d.legal_basis or "") + " " + (d.full_text or ""))
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
            edge = (dkey, resolved, tdate, number_text)
            if edge in seen:
                continue
            seen.add(edge)
            edges.append(edge)
    return edges


def apply_decision_citations(store, decisions: Optional[List] = None) -> Dict[str, int]:
    """Materialize ``:based_on`` edges between PatentDecision and Article nodes."""
    if decisions is None:
        # The graph nodes do not persist full_text (only text_preview), so re-parse
        # the corpus to get the full decisions for reference extraction.
        from .load_decisions_neo4j import scan_decisions, _DECISION_ROOT

        decisions, _raw, _errs = scan_decisions(_DECISION_ROOT)

    articles = load_articles(store)
    plan = build_decision_citation_plan(decisions, articles)
    rows = [
        {"cn": cn, "di": di, "afn": afn, "asd": asd or "", "anum": anum}
        for (dkey, afn, asd, anum) in plan
        for cn, di in [dkey.split("::", 1)]
    ]
    if rows:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (d:PatentDecision {case_number:r.cn, decision_id:r.di}) "
            "MATCH (a:Article {full_name:r.afn, source_date:r.asd, number:r.anum}) "
            "MERGE (d)-[:based_on]->(a)",
            {"rows": rows},
        )
    return {"based_on": len(plan), "decisions": len(decisions)}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build the decision->statute based_on graph.")
    parser.add_argument("--dry-run", action="store_true", help="Count resolvable based_on edges only.")
    args = parser.parse_args(argv)

    from .load_laws_neo4j import make_store
    from .load_decisions_neo4j import scan_decisions, _DECISION_ROOT

    store = make_store()
    decisions, _raw, _errs = scan_decisions(_DECISION_ROOT)
    articles = load_articles(store)
    plan = build_decision_citation_plan(decisions, articles)
    if args.dry_run:
        print({"decisions": len(decisions), "based_on": len(plan)})
        return 0
    rows = [
        {"cn": cn, "di": di, "afn": afn, "asd": asd or "", "anum": anum}
        for (dkey, afn, asd, anum) in plan
        for cn, di in [dkey.split("::", 1)]
    ]
    if rows:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (d:PatentDecision {case_number:r.cn, decision_id:r.di}) "
            "MATCH (a:Article {full_name:r.afn, source_date:r.asd, number:r.anum}) "
            "MERGE (d)-[:based_on]->(a)",
            {"rows": rows},
        )
    print({"decisions": len(decisions), "based_on": len(plan)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build ``classified_in`` edges linking patent decisions/patents to IPC nodes.

Each decision carries a (noisy) IPC code field; each patent aggregates the codes
of the decisions that reference it. This module normalises those codes, resolves
each to the most-specific existing ``IpcNode`` (falling back up the hierarchy),
and emits ``(PatentDecision) -[:classified_in]-> (IpcNode)`` and ``(Patent)
-[:classified_in]-> (IpcNode)`` edges. Pure planning is unit-testable; only the
last apply step touches Neo4j.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .load_laws_neo4j import make_store
from .parse_ipc import (
    IpcNode,
    build_ipc_index,
    normalize_ipc_codes,
    parse_ipc_directory,
    resolve_ipc_in_index,
)

_IPC_DIR = "/Users/xujian/projects/宝宸知识库_Raw/IPC分类表/extracted_text"

DecisionEdge = Tuple[str, str, str]  # (case_number, decision_id, ipc_code)
PatentEdge = Tuple[str, str]  # (patent_number, ipc_code)


def build_ipc_link_plan(
    decision_rows: List[Tuple[str, str, str]],
    patent_rows: List[Tuple[str, str]],
    ipc_records: List[IpcNode],
) -> Tuple[List[DecisionEdge], List[PatentEdge]]:
    """Resolve raw IPC fields into ``classified_in`` edge targets (pure).

    Args:
        decision_rows: ``(case_number, decision_id, raw_ipc)`` per decision.
        patent_rows: ``(patent_number, raw_ipc)`` per patent.
        ipc_records: parsed IPC nodes (the resolution index).

    Returns:
        ``(decision_edges, patent_edges)``.
    """
    dec_edges: List[DecisionEdge] = []
    pat_edges: List[PatentEdge] = []
    seen_dec: set = set()
    seen_pat: set = set()
    index = build_ipc_index(ipc_records)

    for cn, di, raw in decision_rows:
        for code in normalize_ipc_codes(raw):
            target = resolve_ipc_in_index(code, index)
            if target is None:
                continue
            edge = (cn, di, target)
            if edge in seen_dec:
                continue
            seen_dec.add(edge)
            dec_edges.append(edge)

    for pn, raw in patent_rows:
        for code in normalize_ipc_codes(raw):
            target = resolve_ipc_in_index(code, index)
            if target is None:
                continue
            edge = (pn, target)
            if edge in seen_pat:
                continue
            seen_pat.add(edge)
            pat_edges.append(edge)

    return dec_edges, pat_edges


def scan_ipc_fields(store) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """Read the raw ipc fields from Neo4j for decisions and patents."""
    dec: List[Tuple[str, str, str]] = []
    pat: List[Tuple[str, str]] = []

    recs = store.execute_query(
        "MATCH (d:PatentDecision) WHERE d.ipc<>'' "
        "RETURN d.case_number AS cn, d.decision_id AS di, d.ipc AS ipc"
    ).get("records", [])
    for r in recs:
        dec.append((r["cn"] or "", r["di"] or "", r["ipc"] or ""))

    recs = store.execute_query(
        "MATCH (p:Patent) WHERE p.ipc<>'' "
        "RETURN p.patent_number AS pn, p.ipc AS ipc"
    ).get("records", [])
    for r in recs:
        pat.append((r["pn"] or "", r["ipc"] or ""))

    return dec, pat


def apply_ipc_links(store, ipc_records: Optional[List[IpcNode]] = None,
                    decision_rows=None, patent_rows=None) -> Dict[str, int]:
    """Materialise ``:classified_in`` edges between decisions/patents and IpcNode."""
    if ipc_records is None:
        ipc_records = parse_ipc_directory(_IPC_DIR)
    if decision_rows is None or patent_rows is None:
        decision_rows, patent_rows = scan_ipc_fields(store)

    dec_edges, pat_edges = build_ipc_link_plan(decision_rows, patent_rows, ipc_records)

    if dec_edges:
        rows = [{"cn": cn, "di": di, "ipc": ipc} for cn, di, ipc in dec_edges]
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (d:PatentDecision {case_number:r.cn, decision_id:r.di}) "
            "MATCH (i:IpcNode {code:r.ipc}) "
            "MERGE (d)-[:classified_in]->(i)",
            {"rows": rows},
        )
    if pat_edges:
        rows = [{"pn": pn, "ipc": ipc} for pn, ipc in pat_edges]
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (p:Patent {patent_number:r.pn}) "
            "MATCH (i:IpcNode {code:r.ipc}) "
            "MERGE (p)-[:classified_in]->(i)",
            {"rows": rows},
        )

    return {
        "decision_classified_in": len(dec_edges),
        "patent_classified_in": len(pat_edges),
    }


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Build decision/patent -> IPC classified_in edges.")
    parser.add_argument("--dir", default=_IPC_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    ipc_records = parse_ipc_directory(args.dir)
    store = make_store()
    decision_rows, patent_rows = scan_ipc_fields(store)
    dec_edges, pat_edges = build_ipc_link_plan(decision_rows, patent_rows, ipc_records)

    if args.dry_run:
        print({"decision_rows": len(decision_rows), "patent_rows": len(patent_rows),
               "decision_classified_in": len(dec_edges), "patent_classified_in": len(pat_edges)})
        return 0

    result = apply_ipc_links(store, ipc_records, decision_rows, patent_rows)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

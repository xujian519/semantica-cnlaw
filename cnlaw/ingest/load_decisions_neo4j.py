"""Load parsed patent invalidation / reexamination decisions into Neo4j (D1).

The loading step is a pure function (build_decision_plan) that dedups decisions,
aggregates a lightweight ``Patent`` node per application/grant number, and emits
``involves`` edges. Applying runs the plan as batch Cypher against Neo4j through
the same Neo4jStore the law corpus uses (incremental MERGE, no clearing).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .load_laws_neo4j import make_store
from .parse_decision import PatentDecision, merge_multipart, parse_decision_markdown

_DECISION_ROOT = "/Users/xujian/projects/宝宸知识库_Raw/无效复审决定"
_DOMAIN = "专利复审无效"
_TEXT_PREVIEW = 1500  # keep the in-graph node label readable


@dataclass
class DecisionPlan:
    """Nodes and edges to write for a corpus of decisions."""

    decisions: List[Dict] = field(default_factory=list)
    patents: List[Dict] = field(default_factory=list)
    involves: List[Tuple[str, str]] = field(default_factory=list)  # (decision_key, patent_number)


def decision_key(case_number: str, decision_id: str) -> str:
    """A stable node key. decision_id is guaranteed non-empty by the caller."""
    return f"{case_number or ''}::{decision_id or ''}"


def _patent_kind_from_case_type(case_type: str) -> str:
    # 无效书以授权公告号为准; 复审书以申请号为准。
    return "grant" if case_type == "无效" else "application"


def build_decision_plan(docs: List[PatentDecision]) -> DecisionPlan:
    """Dedupe decisions and derive Patent nodes + involves edges (pure)."""
    plan = DecisionPlan()

    unique: Dict[str, PatentDecision] = {}
    for d in docs:
        # ensure a non-empty id so MERGE never collides unrelated records
        decision_id = d.decision_id or d.source_file or d.source_path
        key = decision_key(d.case_number, decision_id)
        if key in unique:
            _fill_gaps(unique[key], d)
            continue
        d.decision_id = decision_id
        unique[key] = d

    patent_by_no: Dict[str, Dict[str, str]] = {}

    for key, d in unique.items():
        plan.decisions.append(
            {
                "key": key,
                "case_number": d.case_number or "",
                "decision_id": d.decision_id,
                "case_type": d.case_type,
                "decision_date": d.decision_date,
                "invention_name": d.invention_name,
                "ipc": d.ipc,
                "patent_holder": d.patent_holder,
                "requesting_party": d.requesting_party,
                "application_number": d.application_number or "",
                "application_date": d.application_date,
                "priority_date": d.priority_date,
                "publication_date": d.publication_date,
                "grant_date": d.grant_date,
                "requester_date": d.requester_date,
                "panel": d.panel,
                "legal_basis": d.legal_basis,
                "decision_points": d.decision_points,
                "decision_result": d.decision_result,
                "tech_field": d.tech_field,
                "domain": d.domain,
                "source_path": d.source_path,
                "source_file": d.source_file,
                "file_name": d.file_name,
                "claims_original": d.claims_original,
                "evidence": d.evidence,
                "legal_reasoning": d.legal_reasoning,
                "confidence": d.confidence,
                "text_preview": d.full_text[:_TEXT_PREVIEW],
            }
        )
        pn = d.application_number
        if pn:
            plan.involves.append((key, pn))
            agg = patent_by_no.setdefault(pn, {"patent_number": pn})
            agg["kind"] = agg.get("kind") or _patent_kind_from_case_type(d.case_type)
            for src, dst in (
                ("invention_name", "invention_name"),
                ("ipc", "ipc"),
                ("patent_holder", "patent_holder"),
                ("application_date", "application_date"),
                ("grant_date", "grant_date"),
            ):
                val = getattr(d, src)
                if val and not agg.get(dst):
                    agg[dst] = val

    plan.patents = list(patent_by_no.values())
    return plan


def _fill_gaps(base: PatentDecision, other: PatentDecision) -> None:
    """Fill missing fields on the kept decision from a duplicate sibling."""
    for fname in (
        "decision_date", "invention_name", "ipc", "patent_holder",
        "requesting_party", "application_number", "grant_date",
        "panel", "legal_basis", "decision_points", "decision_result",
    ):
        if not getattr(base, fname) and getattr(other, fname):
            setattr(base, fname, getattr(other, fname))


def _clear(store) -> None:
    store.execute_query("MATCH (n:PatentDecision) DETACH DELETE n")
    store.execute_query("MATCH (n:Patent) DETACH DELETE n")


def ensure_constraints(store) -> None:
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_decision_uniq IF NOT EXISTS "
        "FOR (d:PatentDecision) REQUIRE (d.case_number, d.decision_id) IS UNIQUE"
    )
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_patent_uniq IF NOT EXISTS "
        "FOR (p:Patent) REQUIRE p.patent_number IS UNIQUE"
    )


def apply_decision_plan(plan: DecisionPlan, store) -> Dict[str, int]:
    """Write the plan to Neo4j as batch Cypher (incremental MERGE)."""
    node_rows = plan.decisions
    if node_rows:
        store.execute_query(
            "UNWIND $rows AS r "
            "MERGE (d:PatentDecision {case_number:r.case_number, decision_id:r.decision_id}) "
            "SET d.case_type=r.case_type, d.decision_date=r.decision_date, "
            "d.invention_name=r.invention_name, d.ipc=r.ipc, d.patent_holder=r.patent_holder, "
            "d.requesting_party=r.requesting_party, d.application_number=r.application_number, "
            "d.application_date=r.application_date, d.priority_date=r.priority_date, "
            "d.publication_date=r.publication_date, d.grant_date=r.grant_date, "
            "d.requester_date=r.requester_date, d.panel=r.panel, d.legal_basis=r.legal_basis, "
            "d.decision_points=r.decision_points, d.decision_result=r.decision_result, "
            "d.tech_field=r.tech_field, d.domain=r.domain, d.source_path=r.source_path, "
            "d.source_file=r.source_file, d.file_name=r.file_name, d.claims_original=r.claims_original, "
            "d.evidence=r.evidence, d.legal_reasoning=r.legal_reasoning, d.confidence=r.confidence, "
            "d.text_preview=r.text_preview",
            {"rows": node_rows},
        )

    if plan.patents:
        store.execute_query(
            "UNWIND $rows AS r "
            "MERGE (p:Patent {patent_number:r.patent_number}) "
            "SET p.kind=CASE WHEN r.kind<>'' THEN r.kind ELSE p.kind END, "
            "p.invention_name=CASE WHEN r.invention_name<>'' THEN r.invention_name ELSE p.invention_name END, "
            "p.ipc=CASE WHEN r.ipc<>'' THEN r.ipc ELSE p.ipc END, "
            "p.patent_holder=CASE WHEN r.patent_holder<>'' THEN r.patent_holder ELSE p.patent_holder END, "
            "p.application_date=CASE WHEN r.application_date<>'' THEN r.application_date ELSE p.application_date END, "
            "p.grant_date=CASE WHEN r.grant_date<>'' THEN r.grant_date ELSE p.grant_date END, "
            "p.domain=$domain",
            {"rows": plan.patents, "domain": _DOMAIN},
        )

    if plan.involves:
        rows = [
            {"cn": cn, "di": di, "pn": pn}
            for key, pn in plan.involves
            for cn, di in [key.split("::", 1)]
        ]
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (d:PatentDecision {case_number:r.cn, decision_id:r.di}) "
            "MATCH (p:Patent {patent_number:r.pn}) "
            "MERGE (d)-[:involves]->(p)",
            {"rows": rows},
        )

    return {
        "decisions": len(plan.decisions),
        "patents": len(plan.patents),
        "involves": len(plan.involves),
    }


def scan_decisions(root: str, json_dir: Optional[str] = None, limit: Optional[int] = None):
    """Walk the decision corpus, parse with optional JSON backfill, and merge parts."""
    root = Path(root)
    json_index: Dict[str, Dict] = {}
    if json_dir:
        for jf in Path(json_dir).glob("*.json"):
            try:
                rec = json.loads(jf.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            json_index.setdefault(rec.get("source_file", jf.stem), rec)

    docs: List[PatentDecision] = []
    errors: List[str] = []
    for i, f in enumerate(sorted(root.glob("*.md"))):
        if limit is not None and i >= limit:
            break
        try:
            rec = json_index.get(f.stem) or json_index.get(f.name)
            docs.append(parse_decision_markdown(f, rec))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {e}")
    merged = merge_multipart(docs)
    return merged, len(docs), errors


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load patent reexamination/invalidation decisions into Neo4j.")
    parser.add_argument("--root", default=_DECISION_ROOT)
    parser.add_argument("--json-dir", default=None,
                        help="knowledge_base/json sidecar dir used to backfill/validate fields.")
    parser.add_argument("--clear", action="store_true", help="Delete the decision subgraph before loading.")
    parser.add_argument("--dry-run", action="store_true", help="Build the plan and report counts without writing.")
    parser.add_argument("--limit", type=int, default=None, help="Only load the first N files (smoke).")
    args = parser.parse_args(argv)

    docs, raw_count, errors = scan_decisions(args.root, args.json_dir, args.limit)
    plan = build_decision_plan(docs)

    if args.dry_run:
        result = {
            "files": raw_count,
            "errors": len(errors),
            "decisions": len(plan.decisions),
            "patents": len(plan.patents),
            "involves": len(plan.involves),
        }
        print(result)
        return 0

    store = make_store()
    ensure_constraints(store)
    if args.clear:
        _clear(store)
    result = apply_decision_plan(plan, store)
    result["files"] = raw_count
    result["errors"] = len(errors)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

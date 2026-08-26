"""Load parsed patent / IP court judgments into Neo4j (D1 for the judgment corpus).

The loading step is a pure function (build_judgment_plan) that dedups judgments by
case number, aggregates lightweight ``Patent`` nodes per involved patent number,
and emits ``involves`` edges. Because the judgment corpus shares the ``Patent``
node with the reexamination/invalidation decisions, the plan aggregates onto the
same ``{patent_number}`` key and applies patent metadata only when a field is
still empty (so it never clobbers what the decision corpus already wrote).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .load_laws_neo4j import make_store
from .parse_judgment import PatentJudgment, scan_judgment_corpus

_JUDGMENT_ROOTS = [
    "/Users/xujian/projects/宝宸知识库_Raw/专利判决",
    "/Users/xujian/projects/宝宸知识库_Raw/指导性专利判决文书_md",
]
_DOMAIN = "专利判决"
_TEXT_PREVIEW = 1500  # keep the in-graph label readable


@dataclass
class JudgmentPlan:
    """Nodes and edges to write for a corpus of judgments."""

    judgments: List[Dict] = field(default_factory=list)
    patents: List[Dict] = field(default_factory=list)
    involves: List[Tuple[str, str, str]] = field(default_factory=list)  # (cn, jid, patent_number)


def judgment_key(case_number: str, judgment_id: str) -> str:
    """A stable node key; judgment_id is guaranteed non-empty by the parser."""
    return case_number or judgment_id


def build_judgment_plan(docs: List[PatentJudgment]) -> JudgmentPlan:
    """Dedupe judgments and derive Patent nodes + involves edges (pure)."""
    plan = JudgmentPlan()

    unique: Dict[str, PatentJudgment] = {}
    for j in docs:
        jid = j.judgment_id or j.source_file
        key = judgment_key(j.case_number, jid)
        if key in unique:
            _fill_gaps(unique[key], j)
            continue
        j.judgment_id = jid
        unique[key] = j

    patent_by_no: Dict[str, Dict[str, str]] = {}

    for key, j in unique.items():
        cn = j.case_number or ""
        jid = j.judgment_id
        plan.judgments.append(
            {
                "cn": cn,
                "jid": jid,
                "case_type": j.case_type,
                "cause": j.cause,
                "court": j.court,
                "decision_date": j.decision_date,
                "invention_name": j.invention_name,
                "patent_holder": j.patent_holder,
                "plaintiff": j.plaintiff,
                "defendant": j.defendant,
                "panel": j.panel,
                "legal_basis": j.legal_basis,
                "decision_points": j.decision_points,
                "decision_result": j.decision_result,
                "claims": j.claims,
                "legal_reasoning": j.legal_reasoning,
                "application_number": j.application_number,
                "patent_numbers": j.patent_numbers,
                "domain": j.domain,
                "source_path": j.source_path,
                "source_file": j.source_file,
                "file_name": j.file_name,
                "text_preview": j.full_text[:_TEXT_PREVIEW],
            }
        )
        for pn in j.patent_numbers:
            if not pn:
                continue
            plan.involves.append((cn, jid, pn))
            agg = patent_by_no.setdefault(pn, {"patent_number": pn})
            for src, dst in (
                ("invention_name", "invention_name"),
                ("patent_holder", "patent_holder"),
                ("application_number", "application_number"),
            ):
                val = getattr(j, src)
                if val and not agg.get(dst):
                    agg[dst] = val
            if not agg.get("kind"):
                agg["kind"] = "application"

    plan.patents = list(patent_by_no.values())
    return plan


def _fill_gaps(base: PatentJudgment, other: PatentJudgment) -> None:
    """Fill missing fields on the kept judgment from a duplicate sibling."""
    for fname in (
        "decision_date", "court", "invention_name", "patent_holder",
        "plaintiff", "defendant", "panel", "legal_basis", "decision_points",
        "decision_result", "application_number",
    ):
        if not getattr(base, fname) and getattr(other, fname):
            setattr(base, fname, getattr(other, fname))
    base.patent_numbers = list(dict.fromkeys(base.patent_numbers + other.patent_numbers))


def _clear(store) -> None:
    store.execute_query("MATCH (n:PatentJudgment) DETACH DELETE n")


def ensure_constraints(store) -> None:
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_judgment_uniq IF NOT EXISTS "
        "FOR (j:PatentJudgment) REQUIRE (j.case_number, j.judgment_id) IS UNIQUE"
    )
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_patent_uniq IF NOT EXISTS "
        "FOR (p:Patent) REQUIRE p.patent_number IS UNIQUE"
    )


def apply_judgment_plan(plan: JudgmentPlan, store) -> Dict[str, int]:
    """Write the plan to Neo4j as batch Cypher (incremental MERGE)."""
    if plan.judgments:
        store.execute_query(
            "UNWIND $rows AS r "
            "MERGE (j:PatentJudgment {case_number:r.cn, judgment_id:r.jid}) "
            "SET j.case_type=r.case_type, j.cause=r.cause, j.court=r.court, "
            "j.decision_date=r.decision_date, j.invention_name=r.invention_name, "
            "j.patent_holder=r.patent_holder, j.plaintiff=r.plaintiff, j.defendant=r.defendant, "
            "j.panel=r.panel, j.legal_basis=r.legal_basis, j.decision_points=r.decision_points, "
            "j.decision_result=r.decision_result, j.claims=r.claims, j.legal_reasoning=r.legal_reasoning, "
            "j.application_number=r.application_number, j.patent_numbers=r.patent_numbers, "
            "j.domain=r.domain, j.source_path=r.source_path, j.source_file=r.source_file, "
            "j.file_name=r.file_name, j.text_preview=r.text_preview",
            {"rows": plan.judgments},
        )

    if plan.patents:
        # Only fill empty fields so a patent shared with the decision corpus keeps
        # the domain / kind the decision loader assigned.
        store.execute_query(
            "UNWIND $rows AS r "
            "MERGE (p:Patent {patent_number:r.patent_number}) "
            "SET p.kind=CASE WHEN p.kind IS NULL THEN r.kind ELSE p.kind END, "
            "p.invention_name=CASE WHEN r.invention_name<>'' AND p.invention_name IS NULL THEN r.invention_name ELSE p.invention_name END, "
            "p.patent_holder=CASE WHEN r.patent_holder<>'' AND p.patent_holder IS NULL THEN r.patent_holder ELSE p.patent_holder END, "
            "p.domain=CASE WHEN p.domain IS NULL THEN $domain ELSE p.domain END",
            {"rows": plan.patents, "domain": _DOMAIN},
        )

    if plan.involves:
        rows = [
            {"cn": cn, "jid": jid, "pn": pn}
            for cn, jid, pn in plan.involves
        ]
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (j:PatentJudgment {case_number:r.cn, judgment_id:r.jid}) "
            "MATCH (p:Patent {patent_number:r.pn}) "
            "MERGE (j)-[:involves]->(p)",
            {"rows": rows},
        )

    return {
        "judgments": len(plan.judgments),
        "patents": len(plan.patents),
        "involves": len(plan.involves),
    }


def scan_judgments(roots=None, limit: Optional[int] = None):
    """Walk the judgment corpus and parse (merged dedupe)."""
    roots = roots or _JUDGMENT_ROOTS
    merged, raw, errors = scan_judgment_corpus(roots, limit)
    return merged, len(raw), errors


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load patent / IP court judgments into Neo4j.")
    parser.add_argument("--root", nargs="+", default=_JUDGMENT_ROOTS)
    parser.add_argument("--clear", action="store_true", help="Delete the judgment subgraph before loading.")
    parser.add_argument("--dry-run", action="store_true", help="Build the plan and report counts without writing.")
    parser.add_argument("--limit", type=int, default=None, help="Only load the first N files (smoke).")
    args = parser.parse_args(argv)

    docs, raw_count, errors = scan_judgments(args.root, args.limit)
    plan = build_judgment_plan(docs)

    if args.dry_run:
        result = {
            "files": raw_count,
            "errors": len(errors),
            "judgments": len(plan.judgments),
            "patents": len(plan.patents),
            "involves": len(plan.involves),
        }
        print(result)
        return 0

    store = make_store()
    ensure_constraints(store)
    if args.clear:
        _clear(store)
    result = apply_judgment_plan(plan, store)
    result["files"] = raw_count
    result["errors"] = len(errors)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

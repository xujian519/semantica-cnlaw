"""Build an Explorer ContextGraph from the cnlaw Neo4j graph (M4).

load_from_neo4j returns generic entities keyed by numeric node id, which the
Explorer renders poorly. Instead we query Neo4j directly and build entities
with stable, readable ids (legal:full_name@date, art:...#number, cat:name) and
typed edges (has_article / belongs_to_category / supersedes), then feed them to
ContextGraph.build_from_entities_and_relationships.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .load_laws_neo4j import make_store

_ARTICLE_TEXT_PREVIEW = 120  # keep the in-graph node label short


def _doc_id(full_name: str, source_date: str) -> str:
    return f"legal:{full_name}" + (f"@{source_date}" if source_date else "")


def _art_id(full_name: str, source_date: str, number: str) -> str:
    return f"art:{full_name}@{source_date or ''}#{number}"


def _cat_id(name: str) -> str:
    return f"cat:{name}"


def _dec_id(case_number: str, decision_id: str) -> str:
    return f"dec:{case_number or ''}::{decision_id or ''}"


def _judgment_id(case_number: str, judgment_id: str) -> str:
    return f"jug:{case_number or ''}::{judgment_id or ''}"


def _patent_id(patent_number: str) -> str:
    return f"patent:{patent_number}"


def _ipc_id(code: str) -> str:
    return f"ipc:{code}"


def load_law_entities_relationships(store) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Pull the cnlaw graph from Neo4j as (entities, relationships)."""
    def run(query: str) -> List[Dict[str, Any]]:
        return store.execute_query(query).get("records", [])

    entities: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []

    for r in run(
        "MATCH (d:LegalDocument) "
        "RETURN d.full_name AS fn, d.source_date AS sd, d.status AS st, "
        "d.legal_level AS ll, d.file_name AS file, d.domain AS domain"
    ):
        entities.append(
            {
                "id": _doc_id(r["fn"], r["sd"]),
                "type": "LegalDocument",
                "text": r["fn"],
                "metadata": {
                    "status": r["st"],
                    "legal_level": r["ll"],
                    "source_date": r["sd"],
                    "file": r["file"],
                    "domain": r["domain"],
                },
            }
        )

    for r in run("MATCH (c:LegalCategory) RETURN c.name AS name"):
        entities.append({"id": _cat_id(r["name"]), "type": "LegalCategory", "text": r["name"]})

    for r in run(
        "MATCH (a:Article) "
        "RETURN a.full_name AS fn, a.source_date AS sd, a.number AS num, a.text AS text"
    ):
        text = (r["text"] or "")[:_ARTICLE_TEXT_PREVIEW]
        entities.append(
            {
                "id": _art_id(r["fn"], r["sd"], r["num"]),
                "type": "Article",
                "text": text,
                "metadata": {"number": r["num"], "full_name": r["fn"]},
            }
        )

    for r in run(
        "MATCH (d:LegalDocument)-[:has_article]->(a:Article) "
        "RETURN d.full_name AS fn, d.source_date AS sd, a.number AS num"
    ):
        relationships.append(
            {
                "source_id": _doc_id(r["fn"], r["sd"]),
                "target_id": _art_id(r["fn"], r["sd"], r["num"]),
                "type": "has_article",
            }
        )

    for r in run(
        "MATCH (d:LegalDocument)-[:belongs_to_category]->(c:LegalCategory) "
        "RETURN d.full_name AS fn, d.source_date AS sd, c.name AS cat"
    ):
        relationships.append(
            {
                "source_id": _doc_id(r["fn"], r["sd"]),
                "target_id": _cat_id(r["cat"]),
                "type": "belongs_to_category",
            }
        )

    for r in run(
        "MATCH (a:LegalDocument)-[:supersedes]->(b:LegalDocument) "
        "RETURN a.full_name AS afn, a.source_date AS asd, b.full_name AS bfn, b.source_date AS bsd"
    ):
        relationships.append(
            {
                "source_id": _doc_id(r["afn"], r["asd"]),
                "target_id": _doc_id(r["bfn"], r["bsd"]),
                "type": "supersedes",
            }
        )

    for r in run(
        "MATCH (a:Article)-[:cites]->(b:Article) "
        "RETURN a.full_name AS afn, a.source_date AS asd, a.number AS anum, "
        "b.full_name AS bfn, b.source_date AS bsd, b.number AS bnum"
    ):
        relationships.append(
            {
                "source_id": _art_id(r["afn"], r["asd"], r["anum"]),
                "target_id": _art_id(r["bfn"], r["bsd"], r["bnum"]),
                "type": "cites",
            }
        )

    # Patent decisions and patents (D1-D2)
    for r in run(
        "MATCH (d:PatentDecision) RETURN d.case_number AS cn, d.decision_id AS di, "
        "d.invention_name AS name, d.case_type AS ct, d.decision_result AS dr, "
        "d.decision_points AS dp, d.application_number AS an, d.decision_date AS dd, "
        "d.source_file AS sf"
    ):
        entities.append(
            {
                "id": _dec_id(r["cn"], r["di"]),
                "type": "PatentDecision",
                "text": r["name"] or r["di"] or r["cn"] or r["sf"],
                "metadata": {
                    "case_type": r["ct"],
                    "decision_result": r["dr"],
                    "decision_points": (r["dp"] or "")[:120],
                    "application_number": r["an"],
                    "decision_date": r["dd"],
                    "source_file": r["sf"],
                },
            }
        )

    for r in run(
        "MATCH (p:Patent) RETURN p.patent_number AS an, p.invention_name AS name, "
        "p.kind AS kind, p.ipc AS ipc"
    ):
        entities.append(
            {
                "id": _patent_id(r["an"]),
                "type": "Patent",
                "text": r["name"] or r["an"],
                "metadata": {"patent_number": r["an"], "kind": r["kind"], "ipc": r["ipc"]},
            }
        )

    for r in run(
        "MATCH (d:PatentDecision)-[:involves]->(p:Patent) "
        "RETURN d.case_number AS cn, d.decision_id AS di, p.patent_number AS pn"
    ):
        relationships.append(
            {
                "source_id": _dec_id(r["cn"], r["di"]),
                "target_id": _patent_id(r["pn"]),
                "type": "involves",
            }
        )

    for r in run(
        "MATCH (d:PatentDecision)-[:based_on]->(a:Article) "
        "RETURN d.case_number AS cn, d.decision_id AS di, "
        "a.full_name AS afn, a.source_date AS asd, a.number AS anum"
    ):
        relationships.append(
            {
                "source_id": _dec_id(r["cn"], r["di"]),
                "target_id": _art_id(r["afn"], r["asd"], r["anum"]),
                "type": "based_on",
            }
        )

    # Patent judgments (patent / IP court judgments)
    for r in run(
        "MATCH (j:PatentJudgment) RETURN j.case_number AS cn, j.judgment_id AS jid, "
        "j.invention_name AS name, j.case_type AS ct, j.cause AS cause, j.court AS court, "
        "j.decision_result AS dr, j.decision_points AS dp, j.application_number AS an, "
        "j.decision_date AS dd, j.source_file AS sf"
    ):
        entities.append(
            {
                "id": _judgment_id(r["cn"], r["jid"]),
                "type": "PatentJudgment",
                "text": r["name"] or r["jid"] or r["cn"] or r["sf"],
                "metadata": {
                    "case_type": r["ct"],
                    "cause": r["cause"],
                    "court": r["court"],
                    "decision_result": r["dr"],
                    "decision_points": (r["dp"] or "")[:120],
                    "application_number": r["an"],
                    "decision_date": r["dd"],
                    "source_file": r["sf"],
                },
            }
        )

    for r in run(
        "MATCH (j:PatentJudgment)-[:involves]->(p:Patent) "
        "RETURN j.case_number AS cn, j.judgment_id AS jid, p.patent_number AS pn"
    ):
        relationships.append(
            {
                "source_id": _judgment_id(r["cn"], r["jid"]),
                "target_id": _patent_id(r["pn"]),
                "type": "involves",
            }
        )

    for r in run(
        "MATCH (j:PatentJudgment)-[:based_on]->(a:Article) "
        "RETURN j.case_number AS cn, j.judgment_id AS jid, "
        "a.full_name AS afn, a.source_date AS asd, a.number AS anum"
    ):
        relationships.append(
            {
                "source_id": _judgment_id(r["cn"], r["jid"]),
                "target_id": _art_id(r["afn"], r["asd"], r["anum"]),
                "type": "based_on",
            }
        )

    # IPC classification: expose only section/class/subclass in the canvas so the
    # ~77k-node full scheme does not blow up rendering; the full table stays in
    # Neo4j for the browse API. Decisions/patents are linked to their subclass.
    ipc_entities: List[Dict[str, Any]] = []
    subclass_codes: set = set()
    for r in run(
        "MATCH (i:IpcNode) WHERE i.level IN ['section','class','subclass'] "
        "RETURN i.code AS code, i.title AS title, i.level AS level"
    ):
        code = r["code"]
        title = (r["title"] or "").strip()
        text = f"{code} {title}".strip()
        ipc_entities.append(
            {
                "id": _ipc_id(code),
                "type": "IpcNode",
                "text": text,
                "metadata": {"code": code, "level": r["level"], "title": title},
            }
        )
        if r["level"] == "subclass":
            subclass_codes.add(code)
    entities.extend(ipc_entities)
    ipc_ids = {e["id"] for e in ipc_entities}

    for r in run(
        "MATCH (c:IpcNode)-[:parent]->(p:IpcNode) "
        "WHERE c.level IN ['class','subclass'] AND p.level IN ['section','class'] "
        "RETURN c.code AS c, p.code AS p"
    ):
        rel = {
            "source_id": _ipc_id(r["c"]),
            "target_id": _ipc_id(r["p"]),
            "type": "parent",
        }
        if rel["source_id"] in ipc_ids and rel["target_id"] in ipc_ids:
            relationships.append(rel)

    # Link decisions/patents to their subclass IPC node (the most-specific node
    # may be a group/subgroup not shown in the canvas, so hop to the subclass).
    for r in run(
        "MATCH (d:PatentDecision)-[:classified_in]->(i:IpcNode) "
        "WHERE i.level IN ['subclass','group','subgroup'] "
        "RETURN d.case_number AS cn, d.decision_id AS di, i.code AS code"
    ):
        sub = (r["code"] or "")[:4]
        if sub in subclass_codes:
            relationships.append(
                {
                    "source_id": _dec_id(r["cn"], r["di"]),
                    "target_id": _ipc_id(sub),
                    "type": "classified_in",
                }
            )

    for r in run(
        "MATCH (p:Patent)-[:classified_in]->(i:IpcNode) "
        "WHERE i.level IN ['subclass','group','subgroup'] "
        "RETURN p.patent_number AS pn, i.code AS code"
    ):
        sub = (r["code"] or "")[:4]
        if sub in subclass_codes:
            relationships.append(
                {
                    "source_id": _patent_id(r["pn"]),
                    "target_id": _ipc_id(sub),
                    "type": "classified_in",
                }
            )

    return entities, relationships


def build_law_context_graph(store=None):
    """Construct a ContextGraph populated with the cnlaw legal corpus."""
    from semantica.context.context_graph import ContextGraph

    store = store or make_store()
    entities, relationships = load_law_entities_relationships(store)
    graph = ContextGraph()
    graph.build_from_entities_and_relationships(entities, relationships)
    graph._cnlaw_stats = {"entities": len(entities), "relationships": len(relationships)}
    return graph

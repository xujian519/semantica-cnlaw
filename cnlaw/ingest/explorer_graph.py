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

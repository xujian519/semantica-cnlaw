"""Load parsed Chinese legal documents into Neo4j (M1, legal-level L0).

The planning step is a pure function (build_import_plan) that dedups documents
by full_name+source_date, assigns effective status via compute_effective_status,
records category membership, and links version supersedes edges. It is
unit-testable without a database. The loading step (apply_import_plan) runs the
plan as batch Cypher against Neo4j through semantica's Neo4jStore.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .exclusion import should_exclude
from .parse_laws import LawDocument, compute_effective_status, parse_law_markdown

# 与 law-import-plan.md 的纳入范围一致
DEFAULT_CATEGORIES = [
    "宪法",
    "宪法相关法",
    "刑法",
    "民法商法",
    "经济法",
    "行政法",
    "社会法",
    "诉讼与非诉讼程序法",
    "民法典",
    "行政法规",
    "司法解释",
    "部门规章",
    "其他",
]


@dataclass
class ImportPlan:
    """The set of nodes and edges to write for a corpus of parsed documents."""

    nodes: List[Dict] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    belongs: List[Tuple[str, str]] = field(default_factory=list)    # (node_key, category)
    supersedes: List[Tuple[str, str]] = field(default_factory=list)  # (history_key, current_key)


def _doc_key(doc: LawDocument) -> str:
    return f"{doc.full_name}@{doc.source_date or ''}"


def _split_key(key: str) -> Tuple[str, str]:
    full_name, _, source_date = key.partition("@")
    return full_name, source_date


def build_import_plan(docs: List[LawDocument]) -> ImportPlan:
    """Dedupe documents and derive nodes/categories/supersedes edges."""
    by_key: Dict[str, Dict] = {}
    for doc in docs:
        key = _doc_key(doc)
        entry = by_key.get(key)
        if entry is None:
            entry = {"doc": doc, "categories": set()}
            by_key[key] = entry
        entry["categories"].add(doc.category)

    unique_docs = [e["doc"] for e in by_key.values()]
    status = compute_effective_status(unique_docs)

    plan = ImportPlan()
    for key, entry in by_key.items():
        doc = entry["doc"]
        plan.nodes.append(
            {
                "key": key,
                "full_name": doc.full_name,
                "name": doc.name,
                "legal_level": doc.legal_level,
                "status": status.get(id(doc), ""),
                "promulgated_date": doc.promulgated_date,
                "amended_dates": doc.amended_dates,
                "source_date": doc.source_date,
                "file_name": doc.file_name,
                "categories": sorted(entry["categories"]),
            }
        )
        for cat in sorted(entry["categories"]):
            plan.belongs.append((key, cat))

    plan.categories = sorted({c for entry in by_key.values() for c in entry["categories"]})

    # supersedes: within each full_name group, older dated versions point to the newest.
    groups: Dict[str, List[str]] = {}
    for key in by_key:
        groups.setdefault(_split_key(key)[0], []).append(key)
    for keys in groups.values():
        dated = sorted((k for k in keys if _split_key(k)[1]), key=lambda k: _split_key(k)[1])
        if len(dated) >= 2:
            target = dated[-1]  # newest dated version, guaranteed current
            for history in dated[:-1]:
                plan.supersedes.append((history, target))

    return plan


def build_article_plan(docs: List[LawDocument]) -> List[Dict]:
    """Dedupe documents and flatten their articles into Article records.

    Each record carries the owning document key (full_name+source_date) so the
    Article can be attached to the right LegalDocument, plus a stable order.
    """
    seen = set()
    records: List[Dict] = []
    for doc in docs:
        key = _doc_key(doc)
        if key in seen:
            continue
        seen.add(key)
        for order, article in enumerate(doc.articles):
            records.append(
                {
                    "full_name": doc.full_name,
                    "source_date": doc.source_date or "",
                    "number": article.number,
                    "text": article.text,
                    "order": order,
                }
            )
    return records


def scan_and_parse(root, categories: List[str]) -> List[LawDocument]:
    """Walk the category directories, parse legal Markdown, apply exclusion rules."""
    root = Path(root)
    docs: List[LawDocument] = []
    for cat in categories:
        d = root / cat
        if not d.is_dir():
            continue
        for f in d.glob("*.md"):
            doc = parse_law_markdown(f, cat)
            if should_exclude(doc.file_name, doc.full_name, doc.category):
                continue
            docs.append(doc)
    return docs


def _load_env(key: str, default: str) -> str:
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv(key, default)


def make_store():
    """Build a Neo4jStore from the local .env / config."""
    from semantica.graph_store.neo4j_store import Neo4jStore

    return Neo4jStore(
        uri=_load_env("GRAPH_STORE_NEO4J_URI", "bolt://localhost:7687"),
        user=_load_env("GRAPH_STORE_NEO4J_USER", "neo4j"),
        password=_load_env("GRAPH_STORE_NEO4J_PASSWORD", "neo4j"),
        database=_load_env("GRAPH_STORE_NEO4J_DATABASE", "neo4j"),
        encrypted=False,
    )


def ensure_constraints(store) -> None:
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_legal_doc_uniq IF NOT EXISTS "
        "FOR (d:LegalDocument) REQUIRE (d.full_name, d.source_date) IS UNIQUE"
    )
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_article_uniq IF NOT EXISTS "
        "FOR (a:Article) REQUIRE (a.full_name, a.source_date, a.number) IS UNIQUE"
    )


def clear(store) -> None:
    """Delete the cnlaw subgraph (Article/LegalDocument/LegalCategory). Idempotent."""
    store.execute_query("MATCH (n:Article) DETACH DELETE n")
    store.execute_query("MATCH (n:LegalDocument) DETACH DELETE n")
    store.execute_query("MATCH (n:LegalCategory) DETACH DELETE n")


def apply_import_plan(plan: ImportPlan, store) -> Dict[str, int]:
    """Write the plan to Neo4j as batch Cypher."""
    if plan.categories:
        store.execute_query(
            "UNWIND $rows AS name MERGE (c:LegalCategory {name:name})", {"rows": plan.categories}
        )

    node_rows = [
        {
            "full_name": n["full_name"],
            "source_date": n["source_date"] or "",
            "name": n["name"],
            "legal_level": n["legal_level"],
            "status": n["status"],
            "promulgated_date": n["promulgated_date"],
            "amended_dates": n["amended_dates"],
            "file_name": n["file_name"],
        }
        for n in plan.nodes
    ]
    store.execute_query(
        "UNWIND $rows AS r "
        "MERGE (d:LegalDocument {full_name:r.full_name, source_date:r.source_date}) "
        "SET d.name=r.name, d.legal_level=r.legal_level, d.status=r.status, "
        "d.promulgated_date=r.promulgated_date, d.amended_dates=r.amended_dates, "
        "d.file_name=r.file_name",
        {"rows": node_rows},
    )

    if plan.belongs:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (d:LegalDocument {full_name:r.fn, source_date:r.sd}) "
            "MATCH (c:LegalCategory {name:r.cat}) "
            "MERGE (d)-[:belongs_to_category]->(c)",
            {
                "rows": [
                    {"fn": _split_key(k)[0], "sd": _split_key(k)[1], "cat": cat}
                    for k, cat in plan.belongs
                ]
            },
        )

    if plan.supersedes:
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (a:LegalDocument {full_name:r.hfn, source_date:r.hsd}) "
            "MATCH (b:LegalDocument {full_name:r.cfn, source_date:r.csd}) "
            "MERGE (a)-[:supersedes]->(b)",
            {
                "rows": [
                    {
                        "hfn": _split_key(hk)[0],
                        "hsd": _split_key(hk)[1],
                        "cfn": _split_key(ck)[0],
                        "csd": _split_key(ck)[1],
                    }
                    for hk, ck in plan.supersedes
                ]
            },
        )

    return {
        "nodes": len(plan.nodes),
        "categories": len(plan.categories),
        "belongs": len(plan.belongs),
        "supersedes": len(plan.supersedes),
    }


def apply_import_articles(articles: List[Dict], store) -> Dict[str, int]:
    """Attach Article nodes to their LegalDocument with has_article edges."""
    if not articles:
        return {"articles": 0}
    store.execute_query(
        "UNWIND $rows AS r "
        "MATCH (d:LegalDocument {full_name:r.full_name, source_date:r.source_date}) "
        "MERGE (a:Article {full_name:r.full_name, source_date:r.source_date, number:r.number}) "
        "SET a.text=r.text, a.order=r.order "
        "MERGE (d)-[:has_article]->(a)",
        {"rows": articles},
    )
    return {"articles": len(articles)}


def main(argv=None) -> int:
    """CLI: load the cnlaw corpus L0 legal-document level into Neo4j."""
    import argparse

    parser = argparse.ArgumentParser(description="Load cnlaw legal corpus into Neo4j (L0).")
    parser.add_argument("--root", default="/Users/xujian/projects/宝宸知识库_Raw/Laws-1.0.0")
    parser.add_argument("--categories", default=None, help="Comma-separated categories (default: all included).")
    parser.add_argument("--clear", action="store_true", help="Delete the cnlaw subgraph before loading.")
    parser.add_argument("--no-articles", action="store_true", help="Only load L0 documents, skip Article nodes.")
    parser.add_argument("--dry-run", action="store_true", help="Build the plan and report counts without writing.")
    args = parser.parse_args(argv)

    cats = args.categories.split(",") if args.categories else DEFAULT_CATEGORIES
    docs = scan_and_parse(args.root, cats)
    plan = build_import_plan(docs)
    articles = build_article_plan(docs)

    if args.dry_run:
        print(
            {
                "documents": len(docs),
                "nodes": len(plan.nodes),
                "categories": len(plan.categories),
                "belongs": len(plan.belongs),
                "supersedes": len(plan.supersedes),
                "articles": len(articles),
            }
        )
        return 0

    store = make_store()
    ensure_constraints(store)
    if args.clear:
        clear(store)
    result = apply_import_plan(plan, store)
    if not args.no_articles:
        result.update(apply_import_articles(articles, store))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

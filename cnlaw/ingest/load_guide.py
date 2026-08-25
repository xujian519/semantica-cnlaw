"""Load the 专利审查指南 (patent examination guideline) into Neo4j.

The guideline is the core corpus of the patent knowledge base. It is parsed by
``parse_guide`` into chapter ``LegalDocument``s whose ``Article`` nodes are the
numbered sections (e.g. ``2.1.3``), tagged domain='专利' and category='审查指南'.
The 修改对照表 (2023->2026 amendment table) is loaded as a separate document.

Incremental: MERGEs into the existing subgraph. Reuses the shared import plan /
article-apply helpers from ``load_laws_neo4j`` (no graph clearing).
"""

from __future__ import annotations

import os

from .load_laws_neo4j import (
    apply_import_articles,
    apply_import_plan,
    build_article_plan,
    build_import_plan,
    ensure_constraints,
    make_store,
)
from .parse_guide import parse_amendment_markdown, scan_guide_corpus
from .prepare_guide_corpus import OUT_DIR

AMENDMENT_MD = "/Users/xujian/projects/宝宸知识库_Raw/审查指南_md/修改对照表.md"


def build_amendment() -> list:
    """Parse the 2023->2026 amendment comparison table into a document."""
    return [parse_amendment_markdown(AMENDMENT_MD)]


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load the 专利审查指南 corpus into Neo4j (incremental).")
    parser.add_argument("--corpus", default=str(OUT_DIR))
    parser.add_argument("--amendment", default=None, help="Path to 修改对照表.md (default: auto).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    docs = scan_guide_corpus(args.corpus)
    if args.amendment or os.path.exists(AMENDMENT_MD):
        docs += build_amendment()

    plan = build_import_plan(docs)
    articles = build_article_plan(docs)

    if args.dry_run:
        print({
            "documents": len(docs),
            "nodes": len(plan.nodes),
            "categories": plan.categories,
            "belongs": len(plan.belongs),
            "supersedes": len(plan.supersedes),
            "articles": len(articles),
        })
        return 0

    store = make_store()
    ensure_constraints(store)
    result = apply_import_plan(plan, store)
    result.update(apply_import_articles(articles, store))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

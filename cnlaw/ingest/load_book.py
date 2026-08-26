"""Load the 以案说法 (patent review / invalidation typical-cases) book into Neo4j.

The book is parsed by ``parse_book`` into chapter ``LegalDocument``s whose
``Article`` nodes are the numbered 要点 sections (e.g. ``1.1``, ``4.4.1``),
tagged domain='专利', category='书籍' and legal_level='书籍', so the shared
graph loader persists a ``LegalCategory '书籍'`` plus ``belongs_to_category``
edges and the search layer can surface the tag.

Incremental: MERGEs into the existing subgraph (no graph clearing). Reuses the
shared import-plan / article-apply helpers from ``load_laws_neo4j``.
"""

from __future__ import annotations

from .load_laws_neo4j import (
    apply_import_articles,
    apply_import_plan,
    build_article_plan,
    build_import_plan,
    ensure_constraints,
    make_store,
)
from .parse_book import scan_book


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load the 以案说法 book into Neo4j (incremental).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    docs = scan_book()
    plan = build_import_plan(docs)
    articles = build_article_plan(docs)

    if args.dry_run:
        print({
            "documents": len(docs),
            "chapters": len(plan.nodes),
            "categories": plan.categories,
            "belongs": len(plan.belongs),
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

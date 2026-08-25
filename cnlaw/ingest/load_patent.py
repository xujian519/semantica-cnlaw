"""Load the patent knowledge corpus (Layer 4, step 1).

The national patent laws / regulations / judicial interpretations are already in
the graph via the central law corpus (Laws-1.0.0); this module only brings in the
patent-specific instruments that are NOT there (the CNIPA departmental rules and
a 2026 judicial interpretation), and tags every patent-domain instrument with
``domain='专利'`` so the patent knowledge base is a coherent, filterable unit.

* ``scan_patent_corpus`` parses the genuinely-new instruments only. National laws
  are NOT re-ingested here (doing so would attach them to a fresh "法律" category
  node and duplicate merging work); their ``domain`` tag is filled by
  ``backfill_patent_domain``.
* Ingestion is incremental: it MERGEs into the existing Neo4j subgraph (no
  clearing), reusing build_import_plan/apply_import_plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .load_laws_neo4j import (
    apply_import_articles,
    apply_import_plan,
    build_article_plan,
    build_import_plan,
    ensure_constraints,
    make_store,
)
from .parse_laws import parse_law_markdown

PATENT_ROOT = "/Users/xujian/projects/宝宸知识库_Raw"
PATENT_DOMAIN = "专利"

# 仅收录「真正新增」的专利文件（中央法律库未包含的部分）。
# (子路径, 效力层级分类)。地方性法规与技术标准不在此列（不纳入）。
_PATENT_FILES = [
    # 部门规章（国家知识产权局令）
    ("规章/专利代理管理办法.md", "部门规章"),
    ("规章/专利实施强制许可办法.md", "部门规章"),
    ("规章/专利权质押登记办法.md", "部门规章"),
    ("规章/专利标识标注办法.md", "部门规章"),
    ("规章/专利行政执法办法.md", "部门规章"),
    ("规章/关于规范专利申请行为的若干规定.md", "部门规章"),
    ("规章/用于专利程序的生物材料保藏办法.md", "部门规章"),
    # 司法解释（2026 惩罚性赔偿）
    (
        "法律法规司法解释/最高人民法院关于审理侵害知识产权民事纠纷案件适用惩罚性赔偿的解释（法释〔2026〕7号）.md",
        "司法解释",
    ),
]


def scan_patent_corpus(root: str = PATENT_ROOT) -> List:
    """Parse the new patent instruments as LawDocuments with domain='专利'."""
    root = Path(root)
    docs = []
    for rel, cat in _PATENT_FILES:
        path = root / rel
        if not path.exists():
            continue
        docs.append(parse_law_markdown(path, cat, domain=PATENT_DOMAIN))
    return docs


def backfill_patent_domain(store) -> dict:
    """Tag every already-loaded patent instrument with domain='专利'.

    The national patent laws/regulations/judicial interpretations were ingested
    by the central law corpus before the domain property existed; this fills in
    their ``domain`` so the patent knowledge base can be filtered as a unit. A
    document is considered patent-domain iff its full name contains '专利'.
    """
    records = store.execute_query(
        "MATCH (d:LegalDocument) WHERE d.full_name CONTAINS '专利' "
        "SET d.domain='专利' RETURN count(d) AS n"
    ).get("records", [])
    return {"patent_documents": records[0]["n"] if records else 0}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load the patent corpus into Neo4j (incremental).")
    parser.add_argument("--root", default=PATENT_ROOT)
    parser.add_argument("--dry-run", action="store_true", help="Report plan counts without writing.")
    parser.add_argument("--backfill-domain", action="store_true",
                        help="Tag existing patent instruments with domain='专利'.")
    args = parser.parse_args(argv)

    store = make_store()

    if args.backfill_domain:
        print(backfill_patent_domain(store))
        return 0

    docs = scan_patent_corpus(args.root)
    plan = build_import_plan(docs)
    articles = build_article_plan(docs)

    if args.dry_run:
        print(
            {
                "documents": len(docs),
                "nodes": len(plan.nodes),
                "categories": plan.categories,
                "belongs": len(plan.belongs),
                "supersedes": len(plan.supersedes),
                "articles": len(articles),
            }
        )
        return 0

    ensure_constraints(store)
    result = apply_import_plan(plan, store)
    result.update(apply_import_articles(articles, store))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

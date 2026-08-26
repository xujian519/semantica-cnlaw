"""Load the parsed IPC classification table into Neo4j as ``IpcNode`` nodes.

The loading step is a pure function (build_ipc_plan) that flattens the parsed
``IpcNode`` records and derives ``(child, parent)`` tree edges from the code
structure. Applying runs the plan as batch Cypher through the same Neo4jStore
the law corpus uses (incremental MERGE, no clearing by default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .load_laws_neo4j import make_store
from .parse_ipc import IpcNode, VERSION, build_ipc_tree, parse_ipc_directory

_IPC_DIR = "/Users/xujian/projects/宝宸知识库_Raw/IPC分类表/extracted_text"


@dataclass
class IpcPlan:
    """Nodes and parent edges to write for the IPC classification table."""

    nodes: List[Dict] = field(default_factory=list)
    parents: List[Tuple[str, str]] = field(default_factory=list)  # (child_code, parent_code)


def build_ipc_plan(records: List[IpcNode]) -> IpcPlan:
    """Turn parsed IPC nodes into a Neo4j write plan (dedupe + tree edges)."""
    # Defensive: dedupe by code (first wins) so a raw record list can't write a node twice.
    seen: set = set()
    deduped: List[IpcNode] = []
    for n in records:
        if n.code in seen:
            continue
        seen.add(n.code)
        deduped.append(n)

    deduped, parents = build_ipc_tree(deduped)
    plan = IpcPlan()
    plan.nodes = [
        {"code": n.code, "title": n.title, "level": n.level, "version": n.version or VERSION}
        for n in deduped
    ]
    plan.parents = list(parents)
    return plan


def ensure_constraints(store) -> None:
    store.execute_query(
        "CREATE CONSTRAINT cnlaw_ipc_uniq IF NOT EXISTS "
        "FOR (n:IpcNode) REQUIRE n.code IS UNIQUE"
    )


def clear(store) -> None:
    """Delete the IPC subgraph. Doesn't touch the cached decision/patent edges."""
    store.execute_query("MATCH (n:IpcNode) DETACH DELETE n")


def apply_ipc_plan(plan: IpcPlan, store) -> Dict[str, int]:
    """Write the IPC nodes and parent edges to Neo4j (incremental MERGE)."""
    if plan.nodes:
        store.execute_query(
            "UNWIND $rows AS r "
            "MERGE (n:IpcNode {code:r.code}) "
            "SET n.title=r.title, n.level=r.level, n.version=r.version",
            {"rows": plan.nodes},
        )

    if plan.parents:
        rows = [{"child": c, "parent": p} for c, p in plan.parents]
        store.execute_query(
            "UNWIND $rows AS r "
            "MATCH (c:IpcNode {code:r.child}), (p:IpcNode {code:r.parent}) "
            "MERGE (c)-[:parent]->(p)",
            {"rows": rows},
        )

    return {"ipc_nodes": len(plan.nodes), "parent_edges": len(plan.parents)}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Load the IPC classification table into Neo4j.")
    parser.add_argument("--dir", default=_IPC_DIR)
    parser.add_argument("--clear", action="store_true", help="Delete the IPC subgraph before loading.")
    parser.add_argument("--dry-run", action="store_true", help="Report plan counts without writing.")
    args = parser.parse_args(argv)

    records = parse_ipc_directory(args.dir)
    plan = build_ipc_plan(records)

    if args.dry_run:
        print({"ipc_nodes": len(plan.nodes), "parent_edges": len(plan.parents)})
        return 0

    store = make_store()
    ensure_constraints(store)
    if args.clear:
        clear(store)
    result = apply_ipc_plan(plan, store)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

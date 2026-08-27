"""Vectorize case-decision reasoning into a separate FAISS index (Stage D reuse).

An ``CaseDecision`` records one step of a patent analysis (检索 / 区别特征 /
技术启示 / 结论). Embedding its ``scenario`` + ``reasoning`` lets the patent mode
search past case steps by a similar scenario — turning prior analyses into a
searchable, reusable knowledge asset. Reuses the local oMLX embedder; a sidecar
caches metadata so the search path can return hits without per-hit Neo4j calls.

Build with: ./.venv/bin/python -m cnlaw.ingest.vectorize_cases --rebuild
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .load_laws_neo4j import make_store
from .omlx_client import OmlxEmbedder
from .vectorize_articles import chunk, persist

DEFAULT_FAISS_PATH = "./data/vector_store/case_decisions.faiss"
DEFAULT_META_PATH = "./data/vector_meta/case_decisions.json"
DEFAULT_DIMENSION = 1024  # BAAI/bge-m3


def _compose(d: Dict[str, Any]) -> str:
    """The text to embed for one case decision."""
    parts = []
    if d.get("category"):
        parts.append(f"环节：{d['category']}")
    if d.get("scenario"):
        parts.append(f"场景：{d['scenario']}")
    if d.get("reasoning"):
        parts.append(f"依据：{d['reasoning']}")
    if d.get("outcome"):
        parts.append(f"结果：{d['outcome']}")
    return "\n".join(parts)


def fetch_cases() -> List[Dict[str, Any]]:
    """Pull every CaseDecision node from Neo4j."""
    recs = make_store().execute_query(
        "MATCH (c:Case)-[:has_decision]->(d:CaseDecision) "
        "RETURN d.decision_id AS decision_id, d.case_id AS case_id, d.category AS category, "
        "d.scenario AS scenario, d.reasoning AS reasoning, d.outcome AS outcome, "
        "d.source_paths AS source_paths"
    ).get("records", [])
    return [dict(r) for r in recs]


def build_metadata(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "decision_id": d["decision_id"] or "",
        "case_id": d["case_id"] or "",
        "category": d["category"] or "",
        "scenario": d["scenario"] or "",
        "reasoning": d["reasoning"] or "",
        "outcome": d["outcome"] or "",
        "source_paths": d.get("source_paths") or [],
        "text": _compose(d),
    }


def _make_id(d: Dict[str, Any]) -> str:
    return d["decision_id"] or f"{d['case_id']}-{d['decision_id']}"


def build_faiss_store(faiss_path, meta_path, dimension: int = DEFAULT_DIMENSION):
    from semantica.vector_store.faiss_store import FAISSIndex, FAISSStore

    store = FAISSStore(dimension=dimension)
    if Path(faiss_path).exists():
        store.index = FAISSIndex.load(str(faiss_path), dimension)
        if Path(meta_path).exists():
            try:
                ids = json.loads(Path(meta_path).read_text(encoding="utf-8")).get("ids", [])
                if ids:
                    store.index.vector_ids = list(ids)
            except (json.JSONDecodeError, KeyError, OSError):
                pass
    else:
        store.create_index("flat", "inner_product")
    return store


def rebuild(faiss_path: str = DEFAULT_FAISS_PATH, meta_path: str = DEFAULT_META_PATH,
            batch_size: int = 64) -> Dict[str, int]:
    """Rebuild the case-decision index from scratch (the ledger is small)."""
    rows = fetch_cases()
    if not rows:
        return {"cases": 0, "embedded": 0}
    embedder = OmlxEmbedder(sub_batch=4, max_retries=5)
    store = build_faiss_store(faiss_path, meta_path)
    ids: List[str] = []
    meta_by_id: Dict[str, Dict[str, Any]] = {}
    for batch in chunk(rows, batch_size):
        texts = [_compose(d) for d in batch]
        vecs = embedder.embed_batch(texts)
        batch_ids = [_make_id(d) for d in batch]
        batch_meta = [build_metadata(d) for d in batch]
        store.add_vectors(vecs, batch_ids, batch_meta)
        ids.extend(batch_ids)
        for vid, m in zip(batch_ids, batch_meta):
            meta_by_id[vid] = m
    persist(store, Path(meta_path), Path(faiss_path), set(ids), meta_by_id)
    return {"cases": len(rows), "embedded": len(ids)}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild the case-decision semantic index.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild from all CaseDecision nodes.")
    parser.add_argument("--faiss-path", default=DEFAULT_FAISS_PATH)
    parser.add_argument("--meta-path", default=DEFAULT_META_PATH)
    args = parser.parse_args(argv)
    print(rebuild(args.faiss_path, args.meta_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

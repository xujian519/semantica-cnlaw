"""Vectorize patent decisions with bge-m3 into a separate FAISS index (D3).

Each decision is embedded at the document level (title + key fields + claims +
reasoning text). Vectors live in their own FAISS index, separate from the law
article index, with an id->metadata sidecar that caches the composed text so the
search path can return hits without per-hit Neo4j round trips. Resume-safe via
the sidecar's ``done`` list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from .load_decisions_neo4j import _DECISION_ROOT, _DOMAIN, decision_key, scan_decisions
from .omlx_client import OmlxEmbedder
from .vectorize_articles import chunk, load_done_ids, persist

DEFAULT_FAISS_PATH = "./data/vector_store/patent_decisions.faiss"
DEFAULT_META_PATH = "./data/vector_meta/patent_decisions.json"
DEFAULT_DIMENSION = 1024  # BAAI/bge-m3
# Decisions are multi-page; a long composed text overflows oMLX's Metal buffers.
# Cap the embedding text so a single request stays small, and embed in tiny
# sub-batches. Keeps the semantic core (title/result/holding/claims) intact.
MAX_TEXT_CHARS = 4000


def make_id(d) -> str:
    """Stable id for a decision vector (matches the graph node key)."""
    return decision_key(d.case_number, d.decision_id)


def build_text(d) -> str:
    """Compose the document-level text to embed for a decision."""
    parts = []
    if d.invention_name:
        parts.append(f"发明名称：{d.invention_name}")
    if d.case_type:
        parts.append(f"决定类型：{d.case_type}")
    if d.decision_result:
        parts.append(f"结论：{d.decision_result}")
    if d.decision_points:
        parts.append(f"决定要点：{d.decision_points}")
    if d.legal_basis:
        parts.append(f"法律依据：{d.legal_basis}")
    if d.claims_original:
        parts.append(f"权利要求书：{d.claims_original}")
    if d.full_text:
        parts.append(d.full_text)
    return "\n".join(parts)[:MAX_TEXT_CHARS]


def build_metadata(d) -> Dict[str, Any]:
    """Metadata persisted to the sidecar (includes the composed text)."""
    return {
        "decision_id": d.decision_id,
        "case_number": d.case_number,
        "case_type": d.case_type,
        "decision_result": d.decision_result,
        "decision_points": d.decision_points,
        "application_number": d.application_number,
        "invention_name": d.invention_name,
        "legal_basis": d.legal_basis,
        "ipc": d.ipc,
        "source_path": d.source_path,
        "source_file": d.source_file,
        "domain": d.domain or _DOMAIN,
        "text": build_text(d),
    }


def fetch_decisions(root: str = _DECISION_ROOT, json_dir: Optional[str] = None,
                    limit: Optional[int] = None):
    """Re-parse the corpus to obtain decisions with full text for embedding."""
    decisions, _raw, _errs = scan_decisions(root, json_dir, limit)
    return decisions


def vectorize(rows: Iterable, embedder, store_faiss, meta_path, faiss_path,
              batch_size: int = 128, persist_every: int = 10) -> Dict[str, int]:
    """Embed fresh decisions and persist. Resumable via the sidecar's done list."""
    done_ids = load_done_ids(meta_path)
    faiss_path = Path(faiss_path)
    meta_path = Path(meta_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    new_total = 0
    batch_count = 0
    meta_by_id: Dict[str, Dict[str, Any]] = {}
    for batch in chunk(list(rows), batch_size):
        fresh = [d for d in batch if make_id(d) not in done_ids]
        if not fresh:
            continue
        texts = [build_text(d) for d in fresh]
        vectors = embedder.embed_batch(texts)
        ids = [make_id(d) for d in fresh]
        metas = [build_metadata(d) for d in fresh]
        store_faiss.add_vectors(vectors, ids, metas)
        for vid, m in zip(ids, metas):
            meta_by_id[vid] = m
        done_ids.update(ids)
        new_total += len(ids)
        batch_count += 1
        if batch_count % persist_every == 0:
            persist(store_faiss, meta_path, faiss_path, done_ids, meta_by_id)

    persist(store_faiss, meta_path, faiss_path, done_ids, meta_by_id)
    return {"processed": len(rows), "new": new_total, "done": len(done_ids)}


def build_faiss_store(faiss_path, meta_path, dimension: int = DEFAULT_DIMENSION):
    """Create or resume a FAISS store (recovers insertion-order ids from sidecar)."""
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


def build_embedder():
    """Embedder backed by the local oMLX server (bge-m3-mlx-fp16).

    Decisions are long, so submit tiny sub-batches with extra retries to avoid
    oMLX dropping the connection on a Metal buffer overflow.
    """
    return OmlxEmbedder(sub_batch=2, max_retries=5)


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Vectorize patent decisions into a separate FAISS index.")
    parser.add_argument("--root", default=_DECISION_ROOT)
    parser.add_argument("--json-dir", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Only vectorize the first N decisions (smoke).")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--dry-run", action="store_true", help="Count decisions only.")
    parser.add_argument("--faiss-path", default=DEFAULT_FAISS_PATH)
    parser.add_argument("--meta-path", default=DEFAULT_META_PATH)
    args = parser.parse_args(argv)

    rows = fetch_decisions(args.root, args.json_dir, args.limit)
    if args.dry_run:
        print({"decisions": len(rows)})
        return 0

    embedder = build_embedder()
    faiss_store = build_faiss_store(args.faiss_path, args.meta_path)
    result = vectorize(rows, embedder, faiss_store, args.meta_path, args.faiss_path, args.batch_size)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

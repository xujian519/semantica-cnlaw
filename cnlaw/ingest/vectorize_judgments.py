"""Vectorize patent / IP court judgments with bge-m3 into a separate FAISS index (D3).

Each judgment is embedded at the document level (title + key fields + claims +
reasoning text). Vectors live in their own FAISS index, separate from the law
article and decision indices, with an id->metadata sidecar that caches the
composed text so the search path can return hits without per-hit Neo4j round
trips. Resume-safe via the sidecar's ``done`` list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .parse_judgment import PatentJudgment
from .load_judgments_neo4j import _JUDGMENT_ROOTS, judgment_key, scan_judgments
from .omlx_client import OmlxEmbedder
from .vectorize_articles import chunk, load_done_ids, persist

DEFAULT_FAISS_PATH = "./data/vector_store/patent_judgments.faiss"
DEFAULT_META_PATH = "./data/vector_meta/patent_judgments.json"
DEFAULT_DIMENSION = 1024  # BAAI/bge-m3
# Judgments are long; a long composed text overflows oMLX's Metal buffers.
MAX_TEXT_CHARS = 4000


def make_id(j) -> str:
    """Stable id for a judgment vector (matches the graph node key)."""
    return judgment_key(j.case_number, j.judgment_id)


def build_text(j) -> str:
    """Compose the document-level text to embed for a judgment."""
    parts = []
    if j.invention_name:
        parts.append(f"发明名称：{j.invention_name}")
    if j.case_type:
        parts.append(f"案件类型：{j.case_type}")
    if j.cause:
        parts.append(f"案由：{j.cause}")
    if j.court:
        parts.append(f"审理法院：{j.court}")
    if j.decision_date:
        parts.append(f"裁判日期：{j.decision_date}")
    if j.application_number:
        parts.append(f"专利号：{j.application_number}")
    if j.decision_result:
        parts.append(f"判决结果：{j.decision_result}")
    if j.decision_points:
        parts.append(f"裁判要点：{j.decision_points}")
    if j.legal_basis:
        parts.append(f"法律依据：{j.legal_basis}")
    if j.claims:
        parts.append(f"权利要求：{j.claims}")
    if j.legal_reasoning:
        parts.append(j.legal_reasoning)
    if j.full_text:
        parts.append(j.full_text)
    return "\n".join(parts)[:MAX_TEXT_CHARS]


def build_metadata(j) -> Dict[str, Any]:
    """Metadata persisted to the sidecar (includes the composed text)."""
    return {
        "judgment_id": j.judgment_id,
        "case_number": j.case_number,
        "case_type": j.case_type,
        "cause": j.cause,
        "court": j.court,
        "decision_date": j.decision_date,
        "invention_name": j.invention_name,
        "decision_result": j.decision_result,
        "legal_basis": j.legal_basis or "",
        "decision_points": j.decision_points or "",
        "application_number": j.application_number,
        "source_path": j.source_path,
        "source_file": j.source_file,
        "domain": j.domain,
        "text": build_text(j),
    }


def fetch_judgments(roots=None, limit: Optional[int] = None):
    """Re-parse the corpus to obtain judgments with full text for embedding."""
    merged, _raw, _errs = scan_judgments(roots, limit)
    return merged


def vectorize(rows: Iterable, embedder, store_faiss, meta_path, faiss_path,
              batch_size: int = 128, persist_every: int = 10) -> Dict[str, int]:
    """Embed fresh judgments and persist. Resumable via the sidecar's done list."""
    done_ids = load_done_ids(meta_path)
    faiss_path = Path(faiss_path)
    meta_path = Path(meta_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    new_total = 0
    batch_count = 0
    meta_by_id: Dict[str, Dict[str, Any]] = {}
    for batch in chunk(list(rows), batch_size):
        fresh = [j for j in batch if make_id(j) not in done_ids]
        if not fresh:
            continue
        texts = [build_text(j) for j in fresh]
        vectors = embedder.embed_batch(texts)
        ids = [make_id(j) for j in fresh]
        metas = [build_metadata(j) for j in fresh]
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

    Judgments are long, so submit tiny sub-batches with extra retries to avoid
    oMLX dropping the connection on a Metal buffer overflow.
    """
    return OmlxEmbedder(sub_batch=2, max_retries=5)


def backfill_fields(meta_path: str = DEFAULT_META_PATH, roots=None) -> Dict[str, int]:
    """Backfill ``legal_basis`` / ``decision_points`` into the judgment sidecar.

    The parser already extracts these; the sidecar omits them. This re-parses the
    corpus once and writes only the id->metadata fields back, reusing the existing
    FAISS vectors — no re-embed — so the ``ground`` filter works on judgments.
    """
    data: Dict[str, Any] = {}
    path = Path(meta_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    meta = data.get("meta", {})
    if not meta:
        return {"judgments": 0, "meta": 0, "updated": 0}

    merged, _raw, _errs = scan_judgments(roots)
    fields = {
        make_id(j): (j.legal_basis or "", j.decision_points or "")
        for j in merged
    }
    updated = 0
    for vid, entry in meta.items():
        info = fields.get(vid)
        if not info:
            continue
        basis, points = info
        if basis or points:
            entry["legal_basis"] = basis
            entry["decision_points"] = points
            updated += 1
    data["meta"] = meta
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"judgments": len(merged), "meta": len(meta), "updated": updated}


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Vectorize patent judgments into a separate FAISS index.")
    parser.add_argument("--root", nargs="+", default=_JUDGMENT_ROOTS)
    parser.add_argument("--limit", type=int, default=None, help="Only vectorize the first N judgments (smoke).")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--dry-run", action="store_true", help="Count judgments only.")
    parser.add_argument("--backfill-fields", action="store_true",
                        help="Backfill legal_basis / decision_points into the sidecar without re-embedding.")
    parser.add_argument("--faiss-path", default=DEFAULT_FAISS_PATH)
    parser.add_argument("--meta-path", default=DEFAULT_META_PATH)
    args = parser.parse_args(argv)

    if args.backfill_fields:
        print(backfill_fields(args.meta_path, args.root))
        return 0

    rows = fetch_judgments(args.root, args.limit)
    if args.dry_run:
        print({"judgments": len(rows)})
        return 0

    embedder = build_embedder()
    faiss_store = build_faiss_store(args.faiss_path, args.meta_path)
    result = vectorize(rows, embedder, faiss_store, args.meta_path, args.faiss_path, args.batch_size)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

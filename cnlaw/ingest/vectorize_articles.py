"""Vectorize cnlaw articles with bge-m3 and store into FAISS (M3).

Reads Article nodes from Neo4j, embeds their text with BAAI/bge-m3
(1024-dim, normalized) served by the local oMLX server, and stores vectors in a
FAISS index plus an id->metadata JSON sidecar for resume. The FAISS .save()
only writes the vector index, so vector_ids/metadata must be persisted
separately to survive a restart — that is what the sidecar JSON is for.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from .load_laws_neo4j import make_store
from .omlx_client import OmlxEmbedder

DEFAULT_FAISS_PATH = "./data/vector_store/law_articles.faiss"
DEFAULT_META_PATH = "./data/vector_meta/law_articles.json"
DEFAULT_DIMENSION = 1024  # BAAI/bge-m3

_FIELDS = ("full_name", "source_date", "number", "category", "status", "text", "source_path")


def make_id(record: Dict[str, Any]) -> str:
    """Stable ID for a vector, keyed by document version + article number."""
    return f"{record['full_name']}@{record.get('source_date') or ''}~{record['number']}"


def build_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    """Metadata incl. the full article text, persisted to the sidecar.

    Keeping ``text`` here lets the search path return hits without a per-hit
    Neo4j round-trip; the FAISS index file does not persist metadata.
    """
    return {field: record.get(field) for field in _FIELDS}


def chunk(rows: Iterable, size: int) -> Iterable[List]:
    batch: List = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_done_ids(meta_path) -> Set[str]:
    """The ids already embedded, read from the sidecar's 'done' list."""
    path = Path(meta_path)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("done", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def fetch_articles(store, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pull articles from Neo4j, optionally filtered by document status."""
    where = "WHERE d.status=$st AND a.text IS NOT NULL" if status else "WHERE a.text IS NOT NULL"
    params = {"st": status} if status else {}
    result = store.execute_query(
        "MATCH (d:LegalDocument)-[:has_article]->(a:Article) " + where + " "
        "RETURN d.full_name AS full_name, d.source_date AS source_date, "
        "a.number AS number, a.text AS text, d.status AS status, d.path AS source_path, "
        "head([(d)-[:belongs_to_category]->(c) | c.name]) AS category",
        params,
    )
    return result.get("records", [])


def dedupe_by_id(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop article duplicates (same doc version + number) keeping the first."""
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for record in records:
        key = make_id(record)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def vectorize(rows: List[Dict[str, Any]], embedder, store_faiss, meta_path, faiss_path,
              batch_size: int = 256, persist_every: int = 20) -> Dict[str, int]:
    """Embed fresh rows and persist. Returns counts. Resumable via loads."""
    done_ids = load_done_ids(meta_path)
    faiss_path = Path(faiss_path)
    meta_path = Path(meta_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    new_total = 0
    batch_count = 0
    meta_by_id: Dict[str, Dict[str, Any]] = {}
    for batch in chunk(rows, batch_size):
        fresh = [r for r in batch if make_id(r) not in done_ids]
        if not fresh:
            continue
        vectors = embedder.embed_batch([r["text"] for r in fresh])
        ids = [make_id(r) for r in fresh]
        metas = [build_metadata(r) for r in fresh]
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


def persist(store_faiss, meta_path: Path, faiss_path: Path, done_ids: Set[str],
            meta_by_id: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Save the FAISS index and the sidecar (ids, done, and id->meta map).

    ``meta`` merges with any existing sidecar entry so an incremental run keeps
    the metadata of articles embedded in earlier sessions, and so a resumed run
    does not drop the text of previously-embedded rows.
    """
    if store_faiss.index is None:
        return
    faiss_path.parent.mkdir(parents=True, exist_ok=True)
    store_faiss.index.save(str(faiss_path))
    existing_meta: Dict[str, Dict[str, Any]] = {}
    if Path(meta_path).exists():
        try:
            existing_meta = json.loads(Path(meta_path).read_text(encoding="utf-8")).get("meta", {})
        except (json.JSONDecodeError, KeyError, OSError):
            existing_meta = {}
    if meta_by_id:
        existing_meta.update(meta_by_id)
    # 'ids' keeps FAISS insertion order (matches the index); 'done' is the resume set.
    meta_path.write_text(
        json.dumps(
            {
                "ids": list(store_faiss.index.vector_ids),
                "done": sorted(done_ids),
                "meta": existing_meta,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_faiss_store(faiss_path, dimension: int = DEFAULT_DIMENSION):
    """Create or resume a FAISS store (loads the index file if present)."""
    from semantica.vector_store.faiss_store import FAISSIndex, FAISSStore

    store = FAISSStore(dimension=dimension)
    if Path(faiss_path).exists():
        store.index = FAISSIndex.load(str(faiss_path), dimension)
        # FAISSIndex.load does not restore insertion-order ids; recover them
        # from the sidecar so a resumed run keeps ids aligned with the index.
        meta_path = Path(DEFAULT_META_PATH)
        if meta_path.exists():
            try:
                ids = json.loads(meta_path.read_text(encoding="utf-8")).get("ids", [])
                if ids:
                    store.index.vector_ids = list(ids)
            except (json.JSONDecodeError, KeyError, OSError):
                pass
    else:
        store.create_index("flat", "inner_product")
    return store


def backfill_meta(meta_path: str = DEFAULT_META_PATH, status: str = "现行有效") -> Dict[str, int]:
    """Fill the sidecar ``meta`` map (article text etc.) without re-embedding.

    Existing FAISS vectors are reused; we only pull document text from Neo4j and
    write it into the sidecar so the search path stops doing per-hit Neo4j round
    trips. Only ids already present in the FAISS index are kept, so the map stays
    aligned with the index.
    """
    store = make_store()
    rows = dedupe_by_id(fetch_articles(store, status=status))
    meta_by_id = {make_id(r): build_metadata(r) for r in rows}

    data: Dict[str, Any] = {}
    path = Path(meta_path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data.setdefault("ids", [])
    data.setdefault("done", [])
    known = set(data["ids"])
    data["meta"] = {vid: m for vid, m in meta_by_id.items() if vid in known}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"articles": len(rows), "meta": len(data["meta"])}


def build_embedder(device: Optional[str] = None):
    """Build an embedder backed by the local oMLX server (MLX / Metal GPU).

    Encoding runs on the oMLX side (bge-m3-mlx-fp16, 1024-dim, multilingual),
    so this process never loads a model — no torch, no fastembed, no ONNX.
    Unlike the e5 models we used before, bge-m3 needs no query/passage prefix,
    so callers pass raw text.
    """
    return OmlxEmbedder()


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Vectorize cnlaw articles into FAISS.")
    parser.add_argument("--status", default="现行有效", help="Document status to vectorize.")
    parser.add_argument("--all-versions", action="store_true", help="Vectorize every status.")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--dry-run", action="store_true", help="Count articles only.")
    parser.add_argument("--backfill", action="store_true",
                        help="Fill sidecar meta (article text) from Neo4j without re-embedding.")
    parser.add_argument("--faiss-path", default=DEFAULT_FAISS_PATH)
    parser.add_argument("--meta-path", default=DEFAULT_META_PATH)
    args = parser.parse_args(argv)

    if args.backfill:
        print(backfill_meta(args.meta_path))
        return 0

    store = make_store()
    status_filter = None if args.all_versions else args.status
    rows = dedupe_by_id(fetch_articles(store, status=status_filter))

    if args.dry_run:
        print({"articles": len(rows), "status": status_filter or "all"})
        return 0

    faiss_store = build_faiss_store(args.faiss_path)
    embedder = build_embedder()
    result = vectorize(rows, embedder, faiss_store, args.meta_path, args.faiss_path, args.batch_size)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

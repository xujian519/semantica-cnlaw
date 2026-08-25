"""Search helpers shared by the worker CLI and the resident search service.

The model lives on the local oMLX server, so this process only makes HTTP
embedding calls; no torch / fastembed / ONNX is loaded here. The embedder,
FAISS index and Neo4j connection are loaded once per-CLI-run or once in a
resident service and reused across queries.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .vectorize_articles import (
    DEFAULT_FAISS_PATH,
    DEFAULT_META_PATH,
    build_embedder,
    build_faiss_store,
)

Backend = Tuple[Any, Any]

# A "已被修订" (revised/superseded) hit is down-weighted so current versions rank first.
DOWNWEIGHT_REVISED = 0.5
_CURRENT = "现行有效"


def _rank_hits(hits: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Sort hits so current ('现行有效') articles rank first, then by score,
    and truncate to the requested ``k``. Revised articles are still returned
    (marked by their status) but never outrank a current version."""
    hits.sort(key=lambda h: (h["status"] != _CURRENT, -h["score"]))
    return hits[:k]


@lru_cache(maxsize=1)
def load_ordered_ids() -> List[str]:
    """The FAISS insertion-order ids from the sidecar (FAISSIndex.load doesn't restore them)."""
    return json.loads(Path(DEFAULT_META_PATH).read_text(encoding="utf-8")).get("ids", [])


@lru_cache(maxsize=1)
def load_meta() -> Dict[str, Dict[str, Any]]:
    """The id->metadata map (incl. article text) from the sidecar.

    Keeping ``text`` here means a query does not need a per-hit Neo4j round-trip;
    the FAISS index file itself does not store metadata.
    """
    return json.loads(Path(DEFAULT_META_PATH).read_text(encoding="utf-8")).get("meta", {})


def load_backend() -> Backend:
    """Load the embedder and FAISS index once (queries need no Neo4j connection)."""
    return build_embedder(), build_faiss_store(DEFAULT_FAISS_PATH)


def query_with_backend(query: str, k: int, backend: Backend) -> List[Dict[str, Any]]:
    """Run a semantic query against an already-loaded backend.

    Hits are resolved from the sidecar ``meta`` map, so the Neo4j graph store is
    not touched here. If an id is missing from ``meta`` (e.g. an index that was
    not backfilled), the fields fall back to what can be parsed from the vector id.
    """
    embedder, faiss_store = backend
    vector = embedder.embed_batch([query])
    # Fetch a wider window so a down-weighted revised hit does not starve the set
    # of current-version results before ranking.
    raw_k = max(k, k * 3)
    distances, indices = faiss_store.index.index.search(vector, raw_k)
    vec_ids = load_ordered_ids()
    meta = load_meta()

    hits: List[Dict[str, Any]] = []
    for j, i in enumerate(indices[0]):
        if i < 0:
            continue  # FAISS pads with -1 when raw_k exceeds the index size
        vid = vec_ids[i]
        entry = meta.get(vid, {})
        rest = entry.get("source_date") or vid.rpartition("@")[2]
        status = entry.get("status", "")
        score = float(distances[0][j])
        if status == "已被修订":
            score *= DOWNWEIGHT_REVISED
        hits.append(
            {
                "full_name": entry.get("full_name") or vid.rpartition("@")[0],
                "source_date": entry.get("source_date") or rest.partition("~")[0],
                "number": entry.get("number") or rest.partition("~")[2],
                "text": entry.get("text", ""),
                "status": status,
                "source_path": entry.get("source_path", ""),
                "score": score,
            }
        )
    return _rank_hits(hits, k)


def collect_hits(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """Load the backend and run a query (used by the standalone CLI)."""
    return query_with_backend(query, k, load_backend())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args(argv)
    print(json.dumps({"results": collect_hits(args.query, args.k)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

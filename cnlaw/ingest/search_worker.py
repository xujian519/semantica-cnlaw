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

from .load_laws_neo4j import make_store
from .vectorize_articles import (
    DEFAULT_FAISS_PATH,
    DEFAULT_META_PATH,
    build_embedder,
    build_faiss_store,
)

Backend = Tuple[Any, Any, Any]


@lru_cache(maxsize=1)
def load_ordered_ids() -> List[str]:
    """The FAISS insertion-order ids from the sidecar (FAISSIndex.load doesn't restore them)."""
    return json.loads(Path(DEFAULT_META_PATH).read_text(encoding="utf-8")).get("ids", [])


def load_backend() -> Backend:
    """Load the embedder, FAISS index and Neo4j connection once."""
    return build_embedder(), build_faiss_store(DEFAULT_FAISS_PATH), make_store()


def query_with_backend(query: str, k: int, backend: Backend) -> List[Dict[str, Any]]:
    """Run a semantic query against an already-loaded backend."""
    embedder, faiss_store, store = backend
    vector = embedder.embed_batch([query])
    distances, indices = faiss_store.index.index.search(vector, k)
    vec_ids = load_ordered_ids()

    hits: List[Dict[str, Any]] = []
    for j, i in enumerate(indices[0]):
        vid = vec_ids[i]
        full_name = vid.rpartition("@")[0]
        rest = vid.rpartition("@")[2]
        source_date, _, number = rest.partition("~")
        result = store.execute_query(
            "MATCH (d:LegalDocument {full_name:$fn, source_date:$sd})-[:has_article]->(a:Article {number:$num}) "
            "RETURN d.status AS st, a.text AS t",
            {"fn": full_name, "sd": source_date, "num": number},
        )
        rec = result.get("records", [])
        hits.append(
            {
                "full_name": full_name,
                "source_date": source_date,
                "number": number,
                "text": rec[0]["t"] if rec else "",
                "status": rec[0]["st"] if rec else "",
                "score": float(distances[0][j]),
            }
        )
    return hits


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

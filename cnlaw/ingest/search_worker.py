"""Search helpers shared by the worker CLI and the resident search service.

The model lives on the local oMLX server, so this process only makes HTTP
embedding calls; no torch / fastembed / ONNX is loaded here. The embedder,
FAISS index and Neo4j connection are loaded once per-CLI-run or once in a
resident service and reused across queries.
"""

from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .vectorize_articles import (
    DEFAULT_FAISS_PATH,
    DEFAULT_META_PATH,
    build_embedder,
    build_faiss_store,
)
from .vectorize_decisions import (
    DEFAULT_FAISS_PATH as DECISION_FAISS_PATH,
    DEFAULT_META_PATH as DECISION_META_PATH,
    build_faiss_store as build_decision_faiss_store,
)
from .vectorize_judgments import (
    DEFAULT_FAISS_PATH as JUDGMENT_FAISS_PATH,
    DEFAULT_META_PATH as JUDGMENT_META_PATH,
    build_faiss_store as build_judgment_faiss_store,
)

Backend = Tuple[Any, Any]

# A "已被修订" (revised/superseded) hit is down-weighted so current versions rank first.
DOWNWEIGHT_REVISED = 0.5
_CURRENT = "现行有效"

# Chinese and Arabic article/paragraph numerals coexist across the corpus:
# decisions cite 第22条第3款, judgments and stored Article nodes cite Chinese
# numerals. Normalize both sides (see cn_num) so a ``ground`` match and the
# graph by-article queries agree. ``_cn_*`` aliases keep the historical
# names used by callers/tests.
from .cn_num import cn_num_to_int as _cn_num_to_int
from .cn_num import cn_numerals_to_arabic as _cn_numerals_to_arabic


def _authority_tier(category: str | None) -> int:
    """Authority tier of a law-article hit, for precedence-aware ranking.

    Source authority, highest first: 法律法规/司法解释/部门规章 (1) →
    审查指南 (2) → 判例 (3, in the separate decision/judgment indices) →
    书籍 (4, explanatory only). Within the single /search index only 1/2/4
    appear; 判例 is its own endpoint. Newest-effective still outranks score.
    """
    cat = (category or "").strip()
    if cat == "书籍":
        return 4
    if cat == "审查指南":
        return 2
    return 1  # laws / regulations / judicial interpretations / field categories


def _rank_hits(hits: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Sort hits by authority tier, then current-version-first, then score.

    A higher-authority source (法规 > 审查指南 > 书籍) always ranks before a
    lower one regardless of embedding score, so a 书籍 excerpt never outranks
    a statute or guideline on the same query. Truncate to the requested ``k``.
    """
    hits.sort(key=lambda h: (_authority_tier(h.get("category")),
                             h.get("status") != _CURRENT,
                             -h.get("score", 0)))
    return hits[:k]


def _field_filter(hits, *, ground=None, ipc=None, result=None, case_type=None):
    """Post-filter semantic candidate hits by precedent metadata (pure, offline).

    ``ground`` is a substring match on the cited legal basis (e.g. "第22条第3款");
    ``ipc`` is a prefix match on any classification code the decision carries
    (codes are separated by ``,`` / Chinese ``、`` / ``;`` / ``/`` / whitespace);
    ``result`` and ``case_type`` are exact after stripping surrounding space.
    A field the corpus did not populate simply fails its filter, which is honest
    for e.g. judgments, whose sidecar carries no IPC.
    """
    if ground is None and ipc is None and result is None and case_type is None:
        return hits
    if ground is not None:
        ground = _cn_numerals_to_arabic(ground)
    out: List[Dict[str, Any]] = []
    for h in hits:
        if ground is not None:
            basis = _cn_numerals_to_arabic(h.get("legal_basis") or "")
            if ground not in basis:
                continue
        if ipc is not None:
            codes = re.split(r"[,、，;；/\s]+", h.get("ipc") or "")
            if not any(c and c.upper().startswith(ipc.upper()) for c in codes):
                continue
        if result is not None and (h.get("decision_result") or "").strip() != result.strip():
            continue
        if case_type is not None and (h.get("case_type") or "").strip() != case_type.strip():
            continue
        out.append(h)
    return out


def _query_precedent(query: str, k: int, backend: Backend, *,
                     ids_loader, meta_loader, fields: Dict[str, str],
                     ground: str | None = None, ipc: str | None = None,
                     result: str | None = None,
                     case_type: str | None = None) -> List[Dict[str, Any]]:
    """Shared semantic query for the decision / judgment precedent indices.

    Both indices are resolved from a sidecar ``meta`` map (no Neo4j), and both
    post-filter the semantic candidates by precedent metadata (see
    :func:`_field_filter`). The FAISS window widens when a filter is present so a
    narrow filter does not starve the result set. ``fields`` maps each output key
    to the sidecar entry key; ``score`` is appended from the FAISS distance.
    """
    embedder, faiss_store = backend
    vector = embedder.embed_batch([query])
    filtered = ground is not None or ipc is not None or result is not None or case_type is not None
    distances, indices = faiss_store.index.index.search(vector, max(k, k * (10 if filtered else 3)))
    vec_ids = ids_loader()
    meta = meta_loader()

    hits: List[Dict[str, Any]] = []
    for j, i in enumerate(indices[0]):
        if i < 0:
            continue
        vid = vec_ids[i]
        entry = meta.get(vid, {})
        row = {"score": float(distances[0][j])}
        for out_key, entry_key in fields.items():
            row[out_key] = entry.get(entry_key, "")
        hits.append(row)
    return _field_filter(hits, ground=ground, ipc=ipc, result=result, case_type=case_type)[:k]


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
                "domain": entry.get("domain") or "",
                "category": entry.get("category") or "",
                "tier": _authority_tier(entry.get("category")),
                "source_path": entry.get("source_path", ""),
                "score": score,
            }
        )
    return _rank_hits(hits, k)


def load_decision_ordered_ids() -> List[str]:
    """Insertion-order ids for the decision FAISS index (from the sidecar)."""
    return json.loads(Path(DECISION_META_PATH).read_text(encoding="utf-8")).get("ids", [])


def load_decision_meta() -> Dict[str, Dict[str, Any]]:
    """id->metadata for decisions (incl. composed text), from the sidecar."""
    return json.loads(Path(DECISION_META_PATH).read_text(encoding="utf-8")).get("meta", {})


def load_decision_backend() -> Backend:
    """Load the embedder and the decision FAISS index (queries need no Neo4j)."""
    return build_embedder(), build_decision_faiss_store(DECISION_FAISS_PATH, DECISION_META_PATH)


def query_decisions(query: str, k: int, backend: Backend, *,
                    ground: str | None = None, ipc: str | None = None,
                    result: str | None = None, case_type: str | None = None) -> List[Dict[str, Any]]:
    """Run a semantic query against the decision index, resolved from the sidecar.

    Optional ``ground`` / ``ipc`` / ``result`` / ``case_type`` post-filter the
    semantic candidates by precedent metadata (see :func:`_field_filter`); the
    FAISS window widens when a filter is present so a narrow filter does not
    starve the result set. See :func:`_query_precedent` for the shared flow.
    """
    return _query_precedent(
        query, k, backend,
        ids_loader=load_decision_ordered_ids, meta_loader=load_decision_meta,
        fields={
            "decision_id": "decision_id", "case_number": "case_number",
            "case_type": "case_type", "decision_result": "decision_result",
            "decision_points": "decision_points", "legal_basis": "legal_basis",
            "application_number": "application_number", "invention_name": "invention_name",
            "ipc": "ipc", "source_path": "source_path", "source_file": "source_file",
            "text": "text",
        },
        ground=ground, ipc=ipc, result=result, case_type=case_type,
    )


def collect_decision_hits(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """Load the decision backend and run a query (standalone CLI)."""
    return query_decisions(query, k, load_decision_backend())


def load_judgment_ordered_ids() -> List[str]:
    """Insertion-order ids for the judgment FAISS index (from the sidecar)."""
    return json.loads(Path(JUDGMENT_META_PATH).read_text(encoding="utf-8")).get("ids", [])


def load_judgment_meta() -> Dict[str, Dict[str, Any]]:
    """id->metadata for judgments (incl. composed text), from the sidecar."""
    return json.loads(Path(JUDGMENT_META_PATH).read_text(encoding="utf-8")).get("meta", {})


def load_judgment_backend() -> Backend:
    """Load the embedder and the judgment FAISS index (queries need no Neo4j)."""
    return build_embedder(), build_judgment_faiss_store(JUDGMENT_FAISS_PATH, JUDGMENT_META_PATH)


def query_judgments(query: str, k: int, backend: Backend, *,
                    ground: str | None = None, ipc: str | None = None,
                    result: str | None = None, case_type: str | None = None) -> List[Dict[str, Any]]:
    """Run a semantic query against the judgment index, resolved from the sidecar.

    Same optional metadata post-filter as :func:`query_decisions`. The judgment
    sidecar carries no IPC, so ``ipc`` succeeds only for non-empty sidecar IPC,
    which judgments do not have; ``ground`` relies on the `legal_basis` field that
    :func:`~cnlaw.ingest.vectorize_judgments.backfill_fields` populates.
    """
    return _query_precedent(
        query, k, backend,
        ids_loader=load_judgment_ordered_ids, meta_loader=load_judgment_meta,
        fields={
            "judgment_id": "judgment_id", "case_number": "case_number",
            "case_type": "case_type", "cause": "cause", "court": "court",
            "decision_result": "decision_result", "legal_basis": "legal_basis",
            "invention_name": "invention_name", "application_number": "application_number",
            "source_path": "source_path", "source_file": "source_file", "text": "text",
        },
        ground=ground, ipc=ipc, result=result, case_type=case_type,
    )


def collect_judgment_hits(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """Load the judgment backend and run a query (standalone CLI)."""
    return query_judgments(query, k, load_judgment_backend())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--k", type=int, default=8)
    args = parser.parse_args(argv)
    print(json.dumps({"results": collect_hits(args.query, args.k)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

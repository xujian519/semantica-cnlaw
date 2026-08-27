"""BM25 lexical retrieval over cnlaw corpus texts.

The resident semantic search is dense-only (FAISS + bge-m3); a lexical (BM25)
arm adds exact-term recall missing from pure embedding — important for patent
text where a specific claim term or statute reference carries the retrieval
signal. Chinese is tokenized with jieba (``cut_for_search``).

The sidecar meta JSON (already loaded by ``search_worker``) is the corpus of
record: ``ids`` gives FAISS insertion order, ``meta[vid].text`` the document.
Building the BM25 index is a deliberate, idempotent step — tokenizing tens of
thousands of long documents is far too slow to do at query time — so it is
persisted to a pickle next to the sidecar and loaded at query time.

Build (each corpus reads its sidecar, writes ``*_lexical.pkl``)::

    python -m cnlaw.ingest.lexical_search --build decisions
    python -m cnlaw.ingest.lexical_search --build judgments
    python -m cnlaw.ingest.lexical_search --build law

Query (for a quick offline check, no service needed)::

    python -m cnlaw.ingest.lexical_search --query "通信单元" --corpus decisions
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Tuple

import jieba

jieba.setLogLevel(logging.WARNING)
from rank_bm25 import BM25Okapi

log = logging.getLogger(__name__)

# corpus -> (sidecar meta path, lexical pickle path)
_CORPORA: Dict[str, Tuple[str, str]] = {
    "law": ("./data/vector_meta/law_articles.json", "./data/vector_meta/law_articles_lexical.pkl"),
    "decisions": ("./data/vector_meta/patent_decisions.json", "./data/vector_meta/patent_decisions_lexical.pkl"),
    "judgments": ("./data/vector_meta/patent_judgments.json", "./data/vector_meta/patent_judgments_lexical.pkl"),
}

# chars fed to BM25 per doc — the lexical arm is an exact-term *recall* signal,
# it does not need the document tail, so trimming keeps the index lean.
_LEX_LIMIT = 2000


def tokenize(text: str) -> List[str]:
    """Tokenize Chinese text for BM25 (search-friendly jieba cut)."""
    return list(jieba.cut_for_search((text or "").lower()))


def _load_sidecar(meta_path: str) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    path = Path(meta_path)
    if not path.exists():
        raise FileNotFoundError(f"sidecar not found: {meta_path}")
    data = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    return data.get("ids", []), data.get("meta", {})


def build_persist(meta_path: str, pickle_path: str) -> Dict[str, Any]:
    """Build a BM25 index from the sidecar and persist (ids, corpus, bm25).

    Empty-text documents carry no lexical signal, so they are dropped from both
    ``ids`` and ``corpus`` (keeping the two aligned).
    """
    ids, meta = _load_sidecar(meta_path)
    pairs = []
    for vid in ids:
        text = (meta.get(vid, {}).get("text", "") or "")[:_LEX_LIMIT]
        if text.strip():
            pairs.append((vid, text))
    corpus = [t for _, t in pairs]
    keep_ids = [v for v, _ in pairs]
    tokenized = [tokenize(t) for t in corpus]
    bm25 = BM25Okapi(tokenized)

    out = Path(pickle_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        pickle.dump({"ids": keep_ids, "tokenized": tokenized, "bm25": bm25}, fh)
    return {"docs": len(keep_ids), "skipped_empty": len(ids) - len(keep_ids), "pickle": str(out)}


def load(pickle_path: str) -> Tuple[List[str], Any]:
    """Load a persisted (ids, BM25Okapi) pair."""
    with open(pickle_path, "rb") as fh:
        data = pickle.load(fh)
    return data["ids"], data["bm25"]


def query(bm25, ids: List[str], q: str, n: int = 60) -> List[Tuple[str, float]]:
    """Top-``n`` (vid, bm25_score) for a query, over the tokenized ids.

    BM25Okapi returns 0 for documents sharing no query term, so only positive
    scores are returned; the result is ordered best-first.
    """
    if not ids:
        return []
    scores = bm25.get_scores(tokenize(q))
    order = sorted(range(len(scores)), key=lambda i: -scores[i])[:n]
    return [(ids[i], float(scores[i])) for i in order if scores[i] > 0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BM25 lexical index over cnlaw corpus sidecar.")
    parser.add_argument("--build", choices=sorted(_CORPORA), help="build+persist a corpus's lexical index")
    parser.add_argument("--query", help="run a lexical query (index must already be built)")
    parser.add_argument("--corpus", choices=sorted(_CORPORA), default="decisions")
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args(argv)

    if args.build:
        meta_path, pickle_path = _CORPORA[args.build]
        print(json.dumps(build_persist(meta_path, pickle_path), ensure_ascii=False))
        return 0

    if args.query:
        _, pickle_path = _CORPORA[args.corpus]
        ids, bm25 = load(pickle_path)
        hits = [{"id": vid, "score": sc} for vid, sc in query(bm25, ids, args.query, args.n)]
        print(json.dumps({"results": hits}, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

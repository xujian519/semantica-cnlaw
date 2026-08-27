"""Cross-encoder reranker over the local oMLX server.

Ranks a small set of candidate documents against a query with oMLX's rerank
endpoint (``BAAI-bge-reranker-v2-m3-mlx-fp16``, ``/v1/rerank``), which returns
0-1 relevance scores. It follows the same httpx / ``trust_env=False`` / retry
pattern as ``omlx_client`` so loopback is never routed through the host proxy
(which yields 502), and keeps the model on the local MLX server — this process
never loads torch / ONNX.

Documents are trimmed to ``_RERANK_MAX_CHARS`` so an oversized decision body does
not blow the model's 8194-token window.
"""

from __future__ import annotations

import os
import time
from typing import List, Tuple

import httpx

_MODEL = os.environ.get("CNLAW_OMLX_RERANK_MODEL", "BAAI-bge-reranker-v2-m3-mlx-fp16")
_RERANK_MAX_CHARS = 2000
_RETRYABLE = (httpx.RemoteProtocolError, httpx.TimeoutException, httpx.ConnectError,
              httpx.ReadError, httpx.WriteError)


class OmlxReranker:
    """Adapter exposing ``rerank(query, candidates) -> [(id, score)]``.

    ``candidates`` is a list of ``(id, text)`` pairs; the posted ``documents``
    keep the same order, and the returned relevance scores are mapped back by
    ``index`` so the caller can re-order by id without re-sending text.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
        max_retries: int = 3,
    ):
        self.base_url = (base_url or os.environ.get("CNLAW_OMLX_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.api_key = api_key or os.environ.get("CNLAW_OMLX_API_KEY", "781102")
        self.model = model or _MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def rerank(self, query: str, candidates: List[Tuple[str, str]]) -> List[Tuple[str, float]]:
        """Return ``(id, relevance_score)`` sorted by score descending.

        An empty candidate list short-circuits; the number of candidates is
        expected to be small (top-``N`` of a fused recall window).
        """
        if not candidates:
            return []
        ids = [c[0] for c in candidates]
        docs = [(c[1] or "")[:_RERANK_MAX_CHARS] for c in candidates]
        payload = {"model": self.model, "query": query, "documents": docs}
        data = self._post(payload)

        scores = [0.0] * len(docs)
        for r in data.get("results", []):
            i = r.get("index")
            if i is not None and 0 <= i < len(scores):
                scores[i] = float(r.get("relevance_score", 0.0))
        ranked = sorted(zip(ids, scores), key=lambda x: -x[1])
        return ranked

    def _post(self, payload: dict) -> dict:
        url = f"{self.base_url}/v1/rerank"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = httpx.post(url, json=payload, headers=self._headers,
                                  timeout=self.timeout, trust_env=False)
            except _RETRYABLE as exc:
                last_exc = exc
                time.sleep(1 * (2 ** attempt))
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code < 500:
                raise RuntimeError(f"oMLX rerank error ({resp.status_code}): {resp.text[:200]}")
            last_exc = RuntimeError(f"oMLX rerank error ({resp.status_code})")
            time.sleep(1 * (2 ** attempt))
        raise RuntimeError(f"oMLX rerank failed after {self.max_retries} retries: {last_exc}")

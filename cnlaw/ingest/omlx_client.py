"""Embedding client backed by the local oMLX server (MLX / Metal GPU).

Encoding happens entirely on the oMLX side via the OpenAI-compatible
``/v1/embeddings`` endpoint, so this process never loads a model — no torch,
no fastembed, no ONNX — which is what previously segfaulted or crawled on this
Mac. The default model is ``bge-m3-mlx-fp16`` (BAAI/bge-m3, 1024-dim,
multilingual). Batch inputs are forwarded as one request; oMLX slices them by
its own ``embedding_batch_size``.
"""

from __future__ import annotations

import os
import time
from typing import Iterable, List

import httpx
import numpy as np

# Connection-level errors worth retrying (transient, oMLX side).
_RETRYABLE = (httpx.RemoteProtocolError, httpx.TimeoutException, httpx.ConnectError,
              httpx.ReadError, httpx.WriteError)


def _chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


class OmlxEmbedder:
    """Small adapter exposing ``embed_batch`` (matches the old embedder API).

    Inputs are split into ``sub_batch`` submissions so a single request never
    carries thousands of long texts (which caused oMLX to drop the connection).
    Each chunk is retried a few times on transient connection errors.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
        normalize: bool = True,
        sub_batch: int = 8,
        max_retries: int = 3,
    ):
        self.base_url = (base_url or os.environ.get("CNLAW_OMLX_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.api_key = api_key or os.environ.get("CNLAW_OMLX_API_KEY", "781102")
        self.model = model or os.environ.get("CNLAW_OMLX_MODEL", "bge-m3-mlx-fp16")
        self.timeout = timeout
        self.normalize = normalize
        self.sub_batch = sub_batch
        self.max_retries = max_retries
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def embed_batch(self, texts: Iterable[str]) -> np.ndarray:
        """Embed a list of texts -> (n, d) float32 array, L2-normalized."""
        texts = list(texts)
        if not texts:
            return np.array([], dtype=np.float32)

        chunks = [_embed_chunk(self._headers, self.base_url, self.model, c,
                               self.timeout, self.max_retries)
                  for c in _chunked(texts, self.sub_batch)]
        vecs = np.concatenate(chunks, axis=0)

        if self.normalize:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1
            vecs = vecs / norms
        return vecs

    def embed_text(self, text: str) -> np.ndarray:
        return self.embed_batch([text])[0]


def _embed_chunk(headers, base_url, model, chunk, timeout, max_retries) -> np.ndarray:
    """One retryable POST of a single chunk (list of texts)."""
    payload = {"model": model, "input": chunk}
    url = f"{base_url}/v1/embeddings"
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
        except _RETRYABLE as exc:
            last_exc = exc
            time.sleep(1 * (2 ** attempt))
            continue

        if resp.status_code == 200:
            data = resp.json().get("data", [])
            data.sort(key=lambda d: d.get("index", 0))
            return np.array([d["embedding"] for d in data], dtype=np.float32)

        # 4xx is not transient — re-raise immediately. 5xx is retryable.
        if resp.status_code < 500:
            raise RuntimeError(f"oMLX embeddings error ({resp.status_code}): {resp.text[:200]}")
        last_exc = RuntimeError(f"oMLX embeddings error ({resp.status_code})")
        time.sleep(1 * (2 ** attempt))

    raise RuntimeError(f"oMLX embeddings request failed after {max_retries} retries: {last_exc}")

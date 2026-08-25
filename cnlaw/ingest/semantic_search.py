"""Semantic search over cnlaw article vectors (M4, step 2).

The actual embedding/FAISS work runs in the resident search_service process
(the model segfaults inside Explorer, and per-request loading is too slow).
This module is the thin HTTP client the /api/cnlaw/search endpoint calls.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

_SEARCH_SERVICE = os.getenv("CNLAW_SEARCH_SERVICE", "http://127.0.0.1:8100")


def search_law(query: str, k: int = 8) -> List[Dict[str, Any]]:
    """Return the top-k similar articles from the resident search service."""
    import requests

    try:
        resp = requests.get(f"{_SEARCH_SERVICE}/search", params={"q": query, "k": k}, timeout=180)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"语义检索服务不可达（{_SEARCH_SERVICE}）。请先启动："
            "uvicorn cnlaw.ingest.search_service:app --port 8100"
        ) from exc
    return resp.json().get("results", [])

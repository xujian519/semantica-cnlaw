"""Resident semantic-search service (M4, step 2).

Runs in its own process so bge-m3 / torch load does not segfault the Explorer
uvicorn process, and keeps the model in memory so every query is fast after a
one-time cold start. Start it, then point the Explorer endpoint here.

Run with: ./.venv/bin/uvicorn cnlaw.ingest.search_service:app --port 8100
"""

from __future__ import annotations

import os

# Set before anything imports torch (via search_worker) to avoid the OpenMP
# thread-count segfault on macOS, and to use the Apple Silicon GPU.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("CNLAW_EMBED_DEVICE", "mps")

from typing import List

from fastapi import FastAPI, Query
from pydantic import BaseModel

from .search_worker import Backend, load_backend, query_with_backend

app = FastAPI(title="cnlaw semantic search")
_backend: Backend | None = None


class SemHit(BaseModel):
    full_name: str
    source_date: str
    number: str
    text: str
    status: str
    domain: str = ""
    source_path: str
    score: float


class SemResponse(BaseModel):
    query: str
    results: List[SemHit]


@app.on_event("startup")
def _load_backend() -> None:
    global _backend
    _backend = load_backend()


@app.get("/search", response_model=SemResponse)
def search(q: str = Query(...), k: int = 8) -> SemResponse:
    if _backend is None:
        raise RuntimeError("backend not loaded")
    return SemResponse(query=q, results=[SemHit(**h) for h in query_with_backend(q, k, _backend)])


@app.get("/health")
def health() -> dict:
    return {"ready": _backend is not None}

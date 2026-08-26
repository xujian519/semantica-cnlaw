"""cnlaw API router for the Explorer (semantic search over law articles)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .semantic_search import search_decisions, search_judgments, search_law

router = APIRouter(prefix="/api/cnlaw", tags=["cnlaw"])


class LawHit(BaseModel):
    full_name: str
    source_date: str
    number: str
    text: str
    status: str
    domain: str = ""
    category: str = ""
    tier: int = 0
    source_path: str
    score: float


class LawSearchResponse(BaseModel):
    query: str
    results: List[LawHit]


@router.get("/search", response_model=LawSearchResponse)
def law_search(q: str = Query(..., description="自然语言查询"), k: int = 8) -> LawSearchResponse:
    return LawSearchResponse(query=q, results=[LawHit(**hit) for hit in search_law(q, k)])


class DecisionHit(BaseModel):
    decision_id: str
    case_number: str = ""
    case_type: str = ""
    decision_result: str = ""
    decision_points: str = ""
    legal_basis: str = ""
    application_number: str = ""
    invention_name: str = ""
    source_path: str = ""
    source_file: str = ""
    ipc: str = ""
    text: str
    score: float


class DecisionSearchResponse(BaseModel):
    query: str
    results: List[DecisionHit]


@router.get("/search/decisions", response_model=DecisionSearchResponse)
def decision_search(q: str = Query(..., description="自然语言查询"), k: int = 8,
                    ground: str | None = Query(None), ipc: str | None = Query(None),
                    result: str | None = Query(None), case_type: str | None = Query(None)) -> DecisionSearchResponse:
    return DecisionSearchResponse(query=q, results=[DecisionHit(**hit) for hit in search_decisions(
        q, k, ground=ground, ipc=ipc, result=result, case_type=case_type)])


class JudgmentHit(BaseModel):
    judgment_id: str
    case_number: str = ""
    case_type: str = ""
    cause: str = ""
    court: str = ""
    decision_result: str = ""
    legal_basis: str = ""
    invention_name: str = ""
    application_number: str = ""
    source_path: str = ""
    source_file: str = ""
    text: str
    score: float


class JudgmentSearchResponse(BaseModel):
    query: str
    results: List[JudgmentHit]


@router.get("/search/judgments", response_model=JudgmentSearchResponse)
def judgment_search(q: str = Query(..., description="自然语言查询"), k: int = 8,
                    ground: str | None = Query(None), ipc: str | None = Query(None),
                    result: str | None = Query(None), case_type: str | None = Query(None)) -> JudgmentSearchResponse:
    return JudgmentSearchResponse(query=q, results=[JudgmentHit(**hit) for hit in search_judgments(
        q, k, ground=ground, ipc=ipc, result=result, case_type=case_type)])

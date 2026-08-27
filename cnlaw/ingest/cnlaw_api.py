"""cnlaw API router for the Explorer (semantic search over law articles)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .inventive_step import build_inventive_bundle
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
    citation_verified: bool = False


class LawSearchResponse(BaseModel):
    query: str
    results: List[LawHit]


@router.get("/search", response_model=LawSearchResponse)
def law_search(q: str = Query(..., description="自然语言查询"), k: int = 8,
               hybrid: bool = Query(True, description="dense+BM25 混合召回；false=纯语义")) -> LawSearchResponse:
    return LawSearchResponse(query=q, results=[LawHit(**hit) for hit in search_law(q, k, hybrid=hybrid)])


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
    citation_verified: bool = False


class DecisionSearchResponse(BaseModel):
    query: str
    results: List[DecisionHit]


@router.get("/search/decisions", response_model=DecisionSearchResponse)
def decision_search(q: str = Query(..., description="自然语言查询"), k: int = 8,
                    ground: str | None = Query(None), ipc: str | None = Query(None),
                    result: str | None = Query(None), case_type: str | None = Query(None),
                    rerank: bool = Query(True, description="交叉编码重排；false=融合后原序")) -> DecisionSearchResponse:
    return DecisionSearchResponse(query=q, results=[DecisionHit(**hit) for hit in search_decisions(
        q, k, ground=ground, ipc=ipc, result=result, case_type=case_type, rerank=rerank)])


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
    citation_verified: bool = False


class JudgmentSearchResponse(BaseModel):
    query: str
    results: List[JudgmentHit]


@router.get("/search/judgments", response_model=JudgmentSearchResponse)
def judgment_search(q: str = Query(..., description="自然语言查询"), k: int = 8,
                    ground: str | None = Query(None), ipc: str | None = Query(None),
                    result: str | None = Query(None), case_type: str | None = Query(None),
                    rerank: bool = Query(True, description="交叉编码重排；false=融合后原序")) -> JudgmentSearchResponse:
    return JudgmentSearchResponse(query=q, results=[JudgmentHit(**hit) for hit in search_judgments(
        q, k, ground=ground, ipc=ipc, result=result, case_type=case_type, rerank=rerank)])


@router.get("/workflow/inventive-step")
def inventive_step(claim: str = Query(..., description="技术方案描述"),
                   field: str = Query("", description="IPC 前缀（如 H01M），用于限定判例检索"),
                   k: int = Query(5, ge=1, le=20)) -> Dict[str, Any]:
    """创造性三步法证据包：输入技术方案，输出 D1/区别特征/技术问题/技术启示四步的溯源引用。

    每步的每条引用都带 source_path + 法条/指南 reference，供 agent 编排可溯源的
    创造性论证。检索复用 :8100 语义 + Neo4j 图谱（based_on 第22条第3款），不新引入对侧依赖。
    """
    return build_inventive_bundle(claim, field=field, k=k)

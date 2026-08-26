"""Neo4j-backed graph-aware precedent retrieval for the patent mode.

Reuses the citation graph the cnlaw corpus builds (``based_on``: decision /
judgment -> statute Article; ``involves``: decision / judgment -> Patent;
``classified_in``: decision / patent -> IpcNode). These are exact structural
queries that complement the semantic top-k of the resident search_service.

Endpoints
---------
``GET /api/cnlaw/graph/ground?article=<法条>&ipc=<IPC前缀>&k=&offset=``
    Decisions + judgments citing the statute article (via ``based_on``), option-
    ally restricted to an IPC subtree (decisions only — judgments carry no IPC).
    Paginated: ``offset`` skips that many per kind, and the response carries
    ``total_decisions`` / ``total_judgments`` (deduped counts) and ``has_more``.
``GET /api/cnlaw/graph/patent?pn=<专利号>``
    The patent's involved decisions + judgments (via ``involves``) and its IPC.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .cn_num import arabic_to_cn, extract_article_number
from .load_laws_neo4j import make_store

router = APIRouter(prefix="/api/cnlaw/graph", tags=["graph"])
_store_cache = None


def _get_store():
    global _store_cache
    if _store_cache is None:
        _store_cache = make_store()
    return _store_cache


class GroundHit(BaseModel):
    kind: str  # decision | judgment
    id: str
    case_number: str = ""
    case_type: str = ""
    court: str = ""
    decision_result: str = ""
    law: str = ""
    article: str = ""
    source_path: str = ""
    source_file: str = ""


class GroundResponse(BaseModel):
    article: str
    article_number: Optional[int] = None
    ipc: str = ""
    offset: int = 0
    k: int = 30
    total_decisions: int = 0
    total_judgments: int = 0
    has_more: bool = False
    hits: List[GroundHit]


class PatentHit(BaseModel):
    kind: str
    id: str
    case_number: str = ""
    case_type: str = ""
    decision_result: str = ""
    source_path: str = ""
    source_file: str = ""


class PatentResponse(BaseModel):
    patent_number: str
    invention_name: str = ""
    ipc: List[str] = []
    hits: List[PatentHit]


@router.get("/ground", response_model=GroundResponse)
def ground(article: str = Query(..., description="法条引用，如 专利法第22条第3款"),
           law: Optional[str] = Query(None, description="法律名过滤，如 专利法"),
           ipc: Optional[str] = Query(None, description="IPC 分类前缀（仅决定）"),
           k: int = Query(30, ge=1, le=200),
           offset: int = Query(0, ge=0)) -> GroundResponse:
    n = extract_article_number(article)
    if n is None:
        raise HTTPException(400, f"无法从 {article!r} 解析出条号（需含 第X条）")
    cn = "第" + arabic_to_cn(n) + "条"
    ar = f"第{n}条"
    store = _get_store()
    base_where = ("(a.number = $cn OR a.number = $ar) "
                  + (("AND a.full_name CONTAINS $law ") if law else ""))
    dparam: Dict[str, Any] = {"cn": cn, "ar": ar, "k": k, "offset": offset}
    if law:
        dparam["law"] = law
    if ipc:
        dparam["ipc"] = ipc

    # Decisions: optional IPC-subtree restriction (decisions carry classified_in).
    dcount = "MATCH (d:PatentDecision)-[:based_on]->(a:Article) WHERE " + base_where
    dpage = dcount + " "
    if ipc:
        dcount += " WITH d, a MATCH (d)-[:classified_in]->(i:IpcNode) WHERE i.code STARTS WITH $ipc "
        dpage += "WITH d, a MATCH (d)-[:classified_in]->(i:IpcNode) WHERE i.code STARTS WITH $ipc "
    dcount += " RETURN count(DISTINCT d) AS n"
    total_decisions = int(store.execute_query(dcount, dparam).get("records", [{}])[0].get("n", 0))
    dpage += ("RETURN DISTINCT d.case_number AS case_number, d.decision_id AS id, "
              "d.case_type AS case_type, d.decision_result AS decision_result, "
              "a.full_name AS law, a.number AS article, d.source_path AS source_path, "
              "d.source_file AS source_file "
              "ORDER BY case_number, id SKIP $offset LIMIT $k")
    drecs = store.execute_query(dpage, dparam).get("records", [])
    hits = [
        GroundHit(kind="decision", id=r["id"] or "", case_number=r["case_number"] or "",
                  case_type=r["case_type"] or "", decision_result=r["decision_result"] or "",
                  law=r["law"] or "", article=r["article"] or "",
                  source_path=r["source_path"] or "", source_file=r["source_file"] or "")
        for r in drecs
    ]

    # Judgments: no IPC classification in the corpus, so only returned when ipc is
    # not requested (otherwise an IPC filter would have nothing to match).
    total_judgments = 0
    if ipc is None:
        jcount = ("MATCH (j:PatentJudgment)-[:based_on]->(a:Article) WHERE " + base_where +
                  " RETURN count(DISTINCT j) AS n")
        total_judgments = int(store.execute_query(jcount, dparam).get("records", [{}])[0].get("n", 0))
        jq = ("MATCH (j:PatentJudgment)-[:based_on]->(a:Article) WHERE " + base_where +
              "RETURN DISTINCT j.case_number AS case_number, j.judgment_id AS id, "
              "j.case_type AS case_type, j.court AS court, "
              "j.decision_result AS decision_result, a.full_name AS law, a.number AS article, "
              "j.source_path AS source_path, j.source_file AS source_file "
              "ORDER BY case_number, id SKIP $offset LIMIT $k")
        jrecs = store.execute_query(jq, dparam).get("records", [])
        hits += [
            GroundHit(kind="judgment", id=r["id"] or "", case_number=r["case_number"] or "",
                      case_type=r["case_type"] or "", court=r["court"] or "",
                      decision_result=r["decision_result"] or "",
                      law=r["law"] or "", article=r["article"] or "",
                      source_path=r["source_path"] or "", source_file=r["source_file"] or "")
            for r in jrecs
        ]

    n_dec_page = len([h for h in hits if h.kind == "decision"])
    n_jdg_page = len([h for h in hits if h.kind == "judgment"])
    has_more = ((offset + n_dec_page) < total_decisions
                or (ipc is None and (offset + n_jdg_page) < total_judgments))
    return GroundResponse(article=article, article_number=n, ipc=ipc or "", offset=offset, k=k,
                          total_decisions=total_decisions, total_judgments=total_judgments,
                          has_more=has_more, hits=hits)


@router.get("/patent", response_model=PatentResponse)
def patent(pn: str = Query(..., description="专利申请/授权号，如 95116452.X")) -> PatentResponse:
    store = _get_store()
    recs = store.execute_query(
        "MATCH (p:Patent) WHERE p.patent_number = $pn "
        "RETURN p.patent_number AS pn, p.invention_name AS name",
        {"pn": pn},
    ).get("records", [])
    if not recs:
        raise HTTPException(404, f"未找到专利 {pn}")
    pn_real = recs[0]["pn"] or pn
    name = recs[0]["name"] or ""

    ipc = [r["code"] for r in store.execute_query(
        "MATCH (p:Patent)-[:classified_in]->(i:IpcNode) WHERE p.patent_number = $pn "
        "RETURN i.code AS code", {"pn": pn_real}).get("records", [])]

    dhits = [
        PatentHit(kind="decision", id=r["id"] or "", case_number=r["case_number"] or "",
                  case_type=r["case_type"] or "", decision_result=r["decision_result"] or "",
                  source_path=r["source_path"] or "", source_file=r["source_file"] or "")
        for r in store.execute_query(
            "MATCH (d:PatentDecision)-[:involves]->(p:Patent) WHERE p.patent_number = $pn "
            "RETURN d.case_number AS case_number, d.decision_id AS id, "
            "d.case_type AS case_type, d.decision_result AS decision_result, "
            "d.source_path AS source_path, d.source_file AS source_file", {"pn": pn_real}).get("records", [])
    ]
    jhits = [
        PatentHit(kind="judgment", id=r["id"] or "", case_number=r["case_number"] or "",
                  case_type=r["case_type"] or "", decision_result=r["decision_result"] or "",
                  source_path=r["source_path"] or "", source_file=r["source_file"] or "")
        for r in store.execute_query(
            "MATCH (j:PatentJudgment)-[:involves]->(p:Patent) WHERE p.patent_number = $pn "
            "RETURN j.case_number AS case_number, j.judgment_id AS id, "
            "j.case_type AS case_type, j.decision_result AS decision_result, "
            "j.source_path AS source_path, j.source_file AS source_file", {"pn": pn_real}).get("records", [])
    ]
    return PatentResponse(patent_number=pn_real, invention_name=name, ipc=ipc, hits=dhits + jhits)

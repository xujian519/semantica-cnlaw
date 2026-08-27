"""MCP server exposing cnlaw graph/case endpoints as native tools (Stage D tool-ify).

Registers ``cnlaw_graph_ground`` / ``cnlaw_graph_patent`` / ``cnlaw_case_record`` /
``cnlaw_case_get`` / ``cnlaw_case_chain`` / ``cnlaw_case_similar`` as MCP tools,
proxying to the resident :8001 Explorer REST API (the cnlaw service must be up).
Wire into a preset via ``@deepseek-ai/dsh-mcp-client`` so the patent mode gets
these as first-class ``mcp__cnlaw__*`` tools instead of raw curl.

Run (stdio, spawned by the mcp-client):
    ./.venv/bin/python -m cnlaw.ingest.cnlaw_mcp
"""

from __future__ import annotations

import os
from typing import List, Optional

import httpx
from mcp.server.mcpserver import MCPServer

_BASE = os.getenv("CNLAW_API", "http://127.0.0.1:8001")
_client: Optional[httpx.Client] = None


def _get() -> httpx.Client:
    global _client
    if _client is None:
        # trust_env=False so localhost:8001 is hit directly, bypassing any
        # HTTP(S)_PROXY that would otherwise route loopback and 502.
        _client = httpx.Client(base_url=_BASE, timeout=120, trust_env=False)
    return _client


mcp = MCPServer("cnlaw")


@mcp.tool()
def cnlaw_graph_ground(article: str, law: str = "", ipc: str = "", k: int = 30) -> dict:
    """按法条精确找判例（图谱 based_on）。article=法条引用（如 专利法第22条第3款，中/阿数字皆可）；law=法律名消歧（如 专利法）；ipc=IPC前缀进一步限定（仅决定）。返回引用该条的决定+判决（案号/结论/法律/source_path）。"""
    params: dict = {"article": article, "k": k}
    if law:
        params["law"] = law
    if ipc:
        params["ipc"] = ipc
    resp = _get().get("/api/cnlaw/graph/ground", params=params)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def cnlaw_graph_patent(pn: str) -> dict:
    """按专利号追踪其复审/无效及诉讼历史（图谱 involves）。pn=专利申请/授权号（如 95116452.X）。返回专利信息+IPC+相关决定/判决。"""
    resp = _get().get("/api/cnlaw/graph/patent", params={"pn": pn})
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def cnlaw_case_record(case_id: str, category: str, scenario: str = "", reasoning: str = "",
                      outcome: str = "", confidence: float = 0.5,
                      entities: Optional[List[str]] = None,
                      source_paths: Optional[List[str]] = None,
                      title: str = "") -> dict:
    """把分析一步记成案件决策（持久化，自动赋 step 并链成 :next 因果链）。category=环节（检索/区别特征与技术问题/技术启示/结论与答复思路等）；scenario/reasoning/outcome/confidence/entities/source_paths 为决策内容与证据。"""
    body = {"category": category, "scenario": scenario, "reasoning": reasoning,
            "outcome": outcome, "confidence": confidence,
            "entities": entities or [], "source_paths": source_paths or []}
    if title:
        body["title"] = title
    resp = _get().post(f"/api/cnlaw/case/{case_id}/decision", json=body)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def cnlaw_case_get(case_id: str) -> dict:
    """读取一个案件的决策链（按步序）。case_id=案件 id。返回全部决策步骤。"""
    resp = _get().get(f"/api/cnlaw/case/{case_id}")
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def cnlaw_case_chain(case_id: str) -> dict:
    """读取一个案件的因果链（每步 → 下一步）。case_id=案件 id。"""
    resp = _get().get(f"/api/cnlaw/case/{case_id}/chain")
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def cnlaw_case_similar(scenario: str, k: int = 8) -> dict:
    """按相似场景检索历史案件决策（复用）。scenario=相似场景描述；返回最相近的历史决策步骤。"""
    resp = _get().get("/api/cnlaw/case/similar", params={"scenario": scenario, "k": k})
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

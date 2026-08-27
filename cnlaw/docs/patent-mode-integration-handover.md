# 专利模式 × semantica-cnlaw 接入 · 交接/复盘文档

> 版本：2026-08-26。项目：`/Users/xujian/projects/semantica-cnlaw`（Semantica 的中文法律/专利环境）与 DeepSeek Harness「专利模式」（`专利模式·CNLaw 底座`）之间的接入。
> 详细设计/端点契约见同目录 `patent-mode-wiring-design.md`；本文件是**总览 + 运维 + 复盘**。

---

## 1. 一句话定位

`semantica-cnlaw` 是一个**自托管、可溯源、可审计的中国法律 + 专利权威环境**；本接入让 DeepSeek Harness 的「专利模式」**充分利用它的四层资源**（权威度 → 语义 → 图谱精确导航 → 案件级审计链），并按权威次序用于专利作业（法律/指南/判例核验、判例定向检索、图谱精确定位、案件分析审计、现有技术检索复用）。

---

## 2. 架构总览

```
┌─ patent 模式（DeepSeek Harness「专利模式·CNLaw 底座」预设）────────────────┐
│  persona（专利代理人＋作业纪律）                                             │
│  skills/  ├─ patent-prior-art-search（可复用现有技术检索例程）[重写]         │
│           └─ 其余专利技能（disclosure/novelty/infringement/invalidity/…）  │
│  mcp-cnlaw ──→ dsh-mcp-client ──→ cnlaw_mcp（MCP server, 6 工具）           │
└──────────────────────────────────────────────────────────────────────────┘
        │ REST(8001/8100) + MCP(stdio)        │ skills
┌─ semantica-cnlaw ─────────────────────────────────────────────────────────┐
│  :8001 explorer_app  ├─ /api/cnlaw/search*        （法条/指南/判例语义）   │
│                      ├─ /api/cnlaw/ipc/*          （IPC 分类树）          │
│                      ├─ /api/cnlaw/graph/*        （基于 based_on/involves/classified_in 精确导航）│
│                      └─ /api/cnlaw/case/*         （案件决策链 + 相似复用） │
│  :8100 search_service ── FAISS 语义检索（法条/决定/判决 case_decisions）     │
│  Neo4j(7687)：法条/决定/判决/专利/审查指南/书籍/IPC + based_on/involves/classified_in/next 边│
│  oMLX(8000)：bge-m3 本地嵌入                                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 依赖与启动（按需）

| 组件 | 端口 | 必须 | 启动 |
|---|---|---|---|
| oMLX（bge-m3 嵌入） | 8000 | ✅ 语义检索/索引 | 启动 `/Applications/oMLX.app` serv（模型 `bge-m3-mlx-fp16`） |
| Neo4j | 7687 | 图谱/IPC/案件链 | `bash bin/start-neo4j.sh` |
| search_service | 8100 | 语义检索 | `set -a && source .env && set +a && ./.venv/bin/uvicorn cnlaw.ingest.search_service:app --port 8100` |
| explorer | 8001 | 图谱/IPC/案件链/前端 | 同上，但 `cnlaw.ingest.explorer_app:app --port 8001` |
| MCP（cnlaw_mcp） | stdio | 原生工具 | 由 dsh-mcp-client 拉起 launcher（`cnlaw_mcp_launcher.py`） |

**常见坑**：本机直连 oMLX/:8001 时，python `urllib`/`httpx` 若 `trust_env=True` 会被宿主代理把 `localhost` 路由成 **502**；`curl` 正常。launcher / cnlaw_mcp 已用 `trust_env=False` 规避。用户自起服务时如遇 502，命令前加 `NO_PROXY="127.0.0.1,localhost"`。

---

## 4. 能力矩阵（六块）

| 块 | 能力 | 端点/技能 | 状态 |
|---|---|---|---|
| **A 权威度核验** | 法条/指南/判例/书籍按权威度排序检索并带 `tier` + `source_path` | `:8100/search`、`:8001/api/cnlaw/search*` | ✅ |
| **B 判例定向检索** | 按 `ground`(法条)/`ipc`/`result`/`case_type` 过滤，命中带 `legal_basis`；中/阿数字归一 | `:8100/search/decisions\|judgments` | ✅ |
| **C 图谱精确导航** | 按法条找判例（based_on）、按专利号追踪（involves）、IPC×法条 | `:8001/api/cnlaw/graph/*` | ✅ |
| **D 案件级审计链** | 每步记成 CaseDecision（`step`+`:next` 链）、读回、因果链 | `:8001/api/cnlaw/case/*` | ✅ |
| **D′ 相似复用** | 按相似场景检索历史案件决策（FAISS） | `:8001/api/cnlaw/case/similar` | ✅ |
| **D″ 工具化** | 上述端点封装为原生 `mcp__cnlaw__*` 工具 | `cnlaw_mcp` + preset `mcp-cnlaw` 行 | ✅ |
| **现有技术检索** | 可复用例程：CNIPR+CNIPA+Google Patents+web_search，产出 D1/D2/D3 | `patent-prior-art-search` 技能 | ✅ 编排/结构化（真实通道需联网+登录态） |

---

## 5. Data 规模（Neo4j / FAISS）

- 决定 29,825｜判决 5,969｜法条约 7 万（法条/行政法规/司法解释/部门规章+域类）｜审查指南 1,193 节｜书籍 358 节｜IPC 79,972 节点
- 图边：`based_on`（决定→法条 67,415 / 判决→法条 19,268）、`involves`（28,623 / 3,038）、`classified_in`（46,463）
- sidecar：`law_articles.faiss`、`patent_decisions.faiss`、`patent_judgments.faiss`、`case_decisions.faiss`（`data/vector_store|meta/`）

---

## 6. 端到端验收记录（真实 patent 会话）

| 阶段 | 验收 | 结果 |
|---|---|---|
| A | 引用《审查指南》/法条原文 + `source_path`；权威度分层 | ✅ `tier=1` 法规排在 `tier=2` 指南前（分数更低也靠前） |
| B | `ground=第22条第3款 + result=维持` → 定向判例（OA 反驳），带 `legal_basis` | ✅ 命中 5 条（含 4W115140/5W133900 正中靶心） |
| C | `graph/ground` 按法条→判例、`graph/patent?pn=95116452.X`→WX4927 | ✅ 200 条/based_on；WX4927 维持有效 + IPC |
| D | 4+ 步 CaseDecision 链 + `case_get`/`case_chain` 读回 | ✅ 95116452X 4 步、silicon-anode 5 步，链闭合，Neo4j 持久化 |
| D′ | `case/similar` 相似复用（诚实不硬套） | ✅ silicon-anode 判 95116452X 技术不可复用，仅方法骨架可复用 |
| D″ | `mcp__cnlaw__*` 工具真实出现在会话并跑通 | ✅ 6 工具全被调用 |

---

## 7. 文件清单（本次接入新增/改动）

**cnlaw 侧**（`/Users/xujian/projects/semantica-cnlaw/`）
- `cnlaw/ingest/search_worker.py`（`_field_filter`、`_authority_tier`、`_rank_hits`、命中带 `legal_basis`/`tier`）
- `cnlaw/ingest/search_service.py`、`cnlaw_api.py`（过滤参数 + `legal_basis`/`tier`）
- `cnlaw/ingest/semantic_search.py`（透传过滤）
- `cnlaw/ingest/vectorize_judgments.py`（侧车存 `legal_basis`/`decision_points` + `--backfill-fields`）
- `cnlaw/ingest/cn_num.py`（中/阿数字归一）｜`graph_api.py`（C1/C2/C3）｜`case_api.py`（决策链 + similar）｜`vectorize_cases.py`（相似复用索引）
- `cnlaw/ingest/cnlaw_mcp.py` + `cnlaw_mcp_launcher.py`（原生工具）
- `cnlaw/ingest/explorer_app.py`（挂载 graph/case router）
- 测试：`cnlaw/tests/test_precedent_filter.py`、`test_cn_num.py`（全套 **164 项通过**）
- 文档：`cnlaw/docs/patent-mode-wiring-design.md`（§1–§11）、本文件

**专利模式侧**（`~/.dsh/.agent-presets/patent-cnlaw/`）
- `agent.cordis.yml`（persona 权威次序/图谱/决策链/MCP 行 + `mcp-cnlaw` 行）
- `skills/patent-prior-art-search/SKILL.md`（可复用现有技术检索例程）
- `preset.yml`（`专利模式·CNLaw 底座`）

**依赖变更**：venv 装了 pypi `mcp`（`pip install "mcp>=0.6"`，2.x，`FastMCP` 已更名 `MCPServer`）。

---

## 8. 已知边界 / 风险

- **判决无 IPC**：`ipc` 过滤仅对决定生效；判决按技术领域用案由/发明名称近似，或走 Neo4j `classified_in`（需按需启动）。
- **字段覆盖**：`decision_points` 只 ~51%（决定）、判决回填后部分；`court` 仅 ~18%；缺失时如实标注、不编造。
- **现有技术检索是外部/脆弱通道**：Google Patents 本机**不可达/503**；CNIPR 需 ego_browser 登录态、PDF 直链须 `http://` 前缀；CNIPA 需官方登录。**离线无法验证命中**（本技能为编排层）。
- **语义检索非精确字段**：`ground` 为子串匹配、多款并引会命中；法条引用仍需 AI 判别（纪律已覆盖）。
- **代理/路由**：`httpx`/`urllib` 对 localhost 会被宿主代理路由 502（`curl` 正常）；cnlaw_mcp 用 `trust_env=False`，自起服务需 `NO_PROXY`。
- **本地 `mcp/` 包遮蔽 pypi `mcp`**：launcher 强制 pypi SDK；未来升级要留意。
- **Neo4j 需按需启动**：图谱/IPC/案件链三块依赖；纯语义（8100 sidecar）不依赖。
- **MCP 工具面**：`mcp__cnlaw__*` 在**真实会话**确认；我已验证 MCP 协议层（工具列表+调用），DSH 挂载由会话收口。

---

## 9. 回滚

- **shipped `patent` 预设从未改动**——只新增了用户级 `patent-cnlaw` 副本；删除 `~/.dsh/.agent-presets/patent-cnlaw/` 即完全回到原始「专利模式」。
- **cnlaw 数据是增量 MERGE、不清库**（各 `load_*` 脚本）；如需回退某层，用对应 `load_*` 的 `--clear` 或重建对应 FAISS 索引即可；不动其它层。
- **服务的退回**：`kill` 8100/8001 + 重启即可；oMLX/Neo4j 独立。

---

## 10. 下一步（未决项）

1. **真实通道验证**：在联网+登录态下，用 `patent-prior-art-search` 走一遍 CNIPR（取 CN 对比文件全文 + 著录项）——这是唯一未端到端实测的块。
2. **`decision_points`/`court` 覆盖率提升**：解析器增强（可选，已在已知边界标注）。
3. **case-decision 增量入索引**：`vectorize_cases --rebuild` 手动跑；可后续做"record 时自动追加"。
4. **把图谱/案件端点做成 DSH 原生工具**（非 MCP，若需要更强 schema/UI 展示）。

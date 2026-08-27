# 开发规范 · semantica-cnlaw

> 本文件是 semantica-cnlaw（Semantica 的中国法律/专利知识环境）的**工程开发规范**。
> 它与上游 `CONTRIBUTING.md`（贡献流程）互补：本文件专注「怎么改代码 / 跑什么门禁 / 哪些是红线」。
> 目标：每条规范都有「家（所在文件）+ 机器门禁 + 理由（决策记录）」，能执行的写死，不能的交给评审，绝不只当散文。

---

## 0. 仓库定位与不变式

一句话：**自托管、可溯源、可审计、本地模型驱动的中国法律 + 专利权威环境**。任何改动都不能破坏以下四条不变式：

1. **数据不出内网**：嵌入走本机 oMLX（`/v1/embeddings`，`:8000`），LLM 抽取走本机 Ollama，零外部 API 依赖。
2. **逐条可溯源**：每条法条/判例/决定/判决断言给得出 `full_name + 条号/案号 + source_path`。
3. **增量、幂等、不清库**：cnlaw 数据是「增量 MERGE、断点续跑」，`load_*`/`vectorize_*` 可重复执行；全量数据留在 Neo4j，画布只是代表性视图。
4. **私有数据不进 git**：宝宸知识库原始数据、向量索引、嵌入/判例侧车、`.env` 一律不进版本库。

---

## 1. 规范三件套（写任何规则前先答三问）

1. **家在哪？** 规则唯一归属一个文件/一层，其余只链接。
2. **谁机器验证？** 必须有 lint / verify 脚本 / CI 门禁能机械拒绝，否则交给语义 review。
3. **理由记在哪？** 为什么这么定、放弃过什么备选，记进决策记录（见 §9）。

**两档执行强度**：能被机械检查的写门禁；不能的（设计取舍、命名语义）交给 code review。**事实清单**（目录表、默认值表、数据规模、端口表）必须从源码/实测生成或配 verify，禁止手编——否则必然漂移。

---

## 2. 工具链与门禁（现状 vs 目标)

### 2.1 Python（主语言）

| 工具 | 配置 | 门禁 |
|---|---|---|
| **black** | `line-length=88`（`[tool.black]`） | pre-commit + flake8 兜底 |
| **isort** | `profile=black`（`[tool.isort]`） | pre-commit |
| **flake8** | `--max-line-length=88 --extend-ignore=E203,W503` | pre-commit |
| **mypy** | `[tool.mypy]` | CI/手动（pre-commit 已注释「手动或 CI」） |
| **pytest** | `testpaths=["tests"]`；`pytest.mark.integration` 排除 | CI + 本地 |

- **新增/改动 Python 代码必须跑**：`pre-commit run --all-files`，且相关测试通过（`cnlaw/tests/` 或 `tests/`）。
- **integration 标记**：需要外部服务（Neo4j/oMLX/API key）的测试打 `@pytest.mark.integration`，默认 `-m "not integration"` 跑；CI / 本地联网时再显式跑。
- **语法与导入自检**：改动后 `python -m py_compile <file>`；改数据管线后 `./.venv/bin/python -m pytest cnlaw/tests -q`。
- **建议新增（负控制）**：在 CI 加一条「断言 `pyproject.toml` 的 `[tool.black].line-length` 仍为 88、`[tool.isort].profile` 仍为 `black`」的 spec，防配置被悄悄放宽而不红。

### 2.2 前端（explorer/）

| 项 | 现状 | 门禁 |
|---|---|---|
| `tsconfig.app.json` | `strict` + `noUnusedLocals/Parameters` + `noFallthroughCasesInSwitch` | `npm run build`（`tsc -b && vite build`） |
| **lint** | `eslint .`（`eslint.config.js`） | `npm run lint` |
| **测试** | `node --test`（graph-store / graph-workspace / plugin-registry） | CI `npm run test:*` |

- 改动 `explorer/src/**`：必须 `tsc -b && vite build` 通过，并跑对应 `npm run test:*`。
- **建议新增（对齐模板最低集）**：`tsconfig.app.json` 补 `noUncheckedIndexedAccess` 与 `exactOptionalPropertyTypes`；新增 `typecheck`（`tsc --noEmit`）并加 CI 门禁——这两条能拦住下标越界与「可选属性显式赋 `undefined`」这类前端高频缺陷（本 PR 的 V8 `Math.max` 溢出即属此类）。
- **若改动 UI/路由/渲染数据**：须按「浏览器验证」流程端到端验证（见 §7.4），且确认各工作区无回归。

### 2.3 统一门禁命令（建议）

```bash
# 一次性跑完核心门禁
cd explorer && npm run lint && npm run build && npm run test:graph-store && npm run test:graph-workspace && npm run test:plugin-registry
./.venv/bin/python -m pytest cnlaw/tests tests -q            # 排除 integration 请加 -m "not integration"
pre-commit run --all-files
```

---

## 3. 提交与版本

- **Conventional Commits**：`feat|fix|docs|test|refactor|perf|style|chore(scope): 描述`。scope 用模块名（`cnlaw`/`explorer`/`seed`/`kg`…）。
- **原子提交 + 粒度上限**：一个提交解决一件事；单个变更尽量 < 800 行。过大的 PR 是「变更传播」风险信号，需拆。
- **PR 关联 issue**：尽量 `Closes #123`。本仓库以跟踪的阶段（如「阶段 A–D」）组织功能，在 PR 描述里引用 `cnlaw/docs` 的设计/交接文档。

---

## 4. 数据与隐私红线（最高优先）

1. **私有原始数据**：宝宸知识库（`/Users/xujian/projects/宝宸知识库_Raw/`：法规库、复审无效决定、判决、审查指南、书籍、IPC 等）**不在仓库内**，绝不在仓库内新增其副本。
2. **`.env` / 密钥**：`.env*` 已在 `.gitignore`；只提交 `.env.example`（占位符）。含 `HF_HUB_OFFLINE`、`SEMANTICA_ALLOW_ANONYMOUS`、`CNLAW_OMLX_URL`、`CNLAW_OMLX_MODEL` 等。禁止提交真实 API key / 代理口令。
3. **生成物不进库**：`data/vector_store/*.faiss`、`data/vector_meta/*.json` 等已 gitignore；侧车 embedding 与判例全文属生成物，不入库。
4. **溯源字段必带**：入库的文档/决定/判决必须写 `source_path`（+ `source_file`）；检索命中必须透传 `source_path`，供审计。
5. **本地模型零外部依赖**：不要引入需要外网 API 的嵌入/抽取路径；新增嵌入或 LLM 调用必须走 oMLX / Ollama，并连同「localhost 代理规避」（见 §6.3）。

---

## 5. cnlaw 数据管线准则

每次新增/修改数据管线（`cnlaw/ingest/`）遵守：

- **增量 MERGE、不清库**：`load_*` 用 `MERGE` 按唯一约束（如 `(full_name, source_date, number)` / `(case_number, decision_id)`）幂等写入；绝不在合流时 `--clear` 整库（那会破坏其它层）。
- **断点续跑**：向量化按 `done`/`id` 侧车续跑，可中断重启；`vectorize_*` 支持 `--limit` / `--rebuild` / `--backfill-*`。
- **嵌入限长与重试**：长文限长（如 4000 字符）+ `sub_batch`/重试，规避 oMLX Metal 溢出（与决定/判决管线一致）。
- **解析器纯函数、可测**：`parse_*` 不碰 DB，输出 dataclass/字典可由单测驱动；真实语料先「画像冒烟」（0 错误、字段分布稳定）再全量。
- **两套边**：`citations.py`（决定/判决 → 法条）复用；`load_*`/`*_citations.py` 建 `based_on`/`involves`/`classified_in` 边，涉及 IPC/专利号时用 `cn_num.py` 归一。
- **画布只是代表视图**：`explorer_graph.py` 的限边（`max_edges_per_hub`）只为交互性，**不能**作为检索/断言依据；全量数据经 `/graph/ground|patent` 精确查询。
- **数据规模事实不进代码**：节点/边/覆盖率等「事实清单」在 `cnlaw/docs/PROGRESS.md` 记录，改动管线后同步更新，别手编进注释。

---

## 6. 服务、端口与运行

| 组件 | 端口 | 依赖 | 启动 |
|---|---|---|---|
| oMLX（bge-m3 嵌入） | `:8000` | 语义检索/索引 | 启动 oMLX serv（`bge-m3-mlx-fp16`） |
| Neo4j | `:7687` | 图谱/IPC/案件链 | `bash bin/start-neo4j.sh` |
| search_service | `:8100` | 语义检索 | `set -a && source .env && set +a && uvicorn cnlaw.ingest.search_service:app --port 8100` |
| explorer | `:8001` | 图谱/IPC/案件链/前端 | 同上，`cnlaw.ingest.explorer_app:app --port 8001` |
| MCP（cnlaw_mcp） | stdio | 原生工具 | 经 `cnlaw_mcp_launcher.py` 拉起 |

**运行要点**：
- 统一载入环境：`source bin/activate-env.sh`。
- **localhost 代理规避**：macOS 系统代理可能把 localhost 路由成 502（curl 正常、python 报错）。凡访问 `:8000`/`:8001`/`:8100` 的 python 客户端用 `trust_env=False`（`httpx`/`requests.Session`），或命令前加 `NO_PROXY="127.0.0.1,localhost"`。`cnlaw_mcp` 已用 `trust_env=False`。
- **同名包冲突**：项目根 `mcp/`（Semantica 自带 MCP server）会遮蔽 pypi `mcp` SDK。`cnlaw_mcp_launcher.py` 用 `sys.path` 重排强制使用 pypi SDK，并已做「命中失败即清晰报错」的自检；**不要**删掉该重排逻辑。根治需上游重命名 `mcp/`，属架构决策，本仓库先以 launcher 兜底。
- **一键脚本**：`bin/build_*.sh`（IPC / 专利判决）支持 `--limit` / `--clear` / `--no-restart`，幂等、可断点；改管线后优先跑对应脚本并确认 `*_ready` 探测。

---

## 7. 测试哲学

1. **真实现优先**：只 mock 昂贵/非确定边界（网络、时钟、外部服务）；mock 绿 ≠ 产品能跑。
2. **测真实入口**：产品可见行为走真实入口（真实 Loader / CLI / REST / 浏览器），不只测手挂的单元组合。
3. **验证世界，不是自述**：断言可重跑的输入/输出、真实 `source_path`、字节一致、Neo4j 实际命中；不信被测对象自己的报告。
4. **覆盖率 = 死代码探测器，不是 KPI**：未覆盖行优先判为该删的死代码，而不是补空测试；禁止用 `--passWithNoTests` / 收窄 `include` / 降阈值来凑数字。
5. **单测 + 端到端分层**：核心纯函数（`cn_num`/`_field_filter`/解析器/引用抽取）用单测钉住行为；跨组件/服务链路用真实服务跑；改 `explorer` 前端用 `cnlaw`/`tests` 的 explorer 相关测试。
6. **负控制**：对关键门禁写「引入回归 → 看红 → 回退」的验证，确保守卫真的在拦。

### 7.4 浏览器验证（UI 变更必做）

改动 UI/布局/样式/路由/客户端状态/渲染数据时，用浏览器工具端到端验证：点击/输入/提交，确认行为而非仅截图；检查共享同一状态的所有页面/路由；主动找回归；空态/错误态/路由变体也验证；桌面与移动视口都看。无浏览器工具时用最接近的替代（curl 真实接口 / 渲染脚本 / 测试），并如实说明未验证项。

---

## 8. 代码评审

- **评审关注设计，不纠结风格**：风格交给 black/isort/flake8/eslint；评审看「设计是否清晰、有无更简单方案、接口契约是否双侧对齐、是否破坏不变式」。
- **铁律必须有门禁或 lint，不能只当散文**。例如：数据隐私红线、增量不清库、溯源必带——要么有校验，要么列为 review 阻断项。
- **可用工具**：`brooks-review` / `brooks-test` / `brooks-sweep`（按 6 大 decay risk + 测试质量审查）；本仓库 PR 曾用其发现并修复「判例查询重复、长函数、缓存无上限、`mcp/` 同名校名冲突」。
- **PR 规模信号**：单 PR > 500 行 / > 10 无关文件，本身是「变更传播」告警，需在评审时说明或拆分。

---

## 9. 决策记录（强制 Alternatives）

非平凡变更（改行为/架构/契约/流程/格式/数据口径）必须在 PR 带决策记录，且**必须**含 `## Alternatives considered`。

格式（放 `cnlaw/docs/` 或仓库 `docs/notes/{status}/{yyyy-mm-dd}-{topic}.md`，status ∈ `proposed|implemented|rejected`）：

```markdown
# Note: <标题>

Status: implemented

## Problem
<不依赖解决方案也能读懂的问题>

## Decision
<已落地的现实，现在时>

## Alternatives considered
- **方案 A** — 为什么落选
- **方案 B** — 为什么落选

## Consequences
<换来了什么、付出了什么>
```

规则：一条决策一个文件；编辑 note 不许改成另一个决策（另写新 note 交叉链接）。已确立的决策如：数据源用中央法规库、时效「文件名最新=现行有效」、嵌入走 oMLX、判决策略含「judgments 无 IPC」等，见 `cnlaw/docs/PROGRESS.md` §5 决策记录。

---

## 10. 落地清单

### 已具备（现状）
- 上游 `CONTRIBUTING.md` 贡献流程；`CHANGELOG.md`；`SECURITY.md`/`CODE_OF_CONDUCT.md`。
- Python：black/isort/flake8 入 pre-commit；mypy 配置在 `pyproject.toml`。
- 前端：`tsc -b` strict + eslint + `node --test` 测试。
- CI：`ci.yml`（前端测试/构建 + Python 包构建 + `requirements-ci.txt` 新鲜度校验）+ codeql / security-scan / defender-for-devops。
- 数据红线：`.env*` / `data/` / `*.faiss` 已 gitignore；私有语料在仓库外。

### 建议下一步（对齐「AI 原生开发规范」最低集）
- 前端 `tsconfig.app.json` 补 `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes`，加 `typecheck` 脚本与 CI 门禁。
- Python 加「配置不被放宽」负控制 spec（black line-length / isort profile）。
- 前端补覆盖率门禁（每文件 100% 或按模块阈值），并纳入 CI。
- 建根 `AGENTS.md`（把本规范压缩为 1–3 行 standing orders + 链接，作为 agent 每次会话的规范宿主），子树 `cnlaw/AGENTS.md` 只放该子树特有命令。
- 补「生成物/事实清单新鲜度」门禁（如 `verify-doc-links`、数据规模从 PROGRESS 生成或校验）。

> 引入节奏：**宁可门禁少而每道真执行，也不要清单长而全靠自觉**。以上「建议下一步」按需逐条加，别第一天背全套。

---

*参考：上游 `CONTRIBUTING.md`；`/Users/xujian/projects/开发规范/`（dev-standards-guide.html、new-project-standards-template.md）；`cnlaw/docs/PROGRESS.md`（进度与决策记录）。*

# 开发进度记录

> 更新日期：2026-08-26。
> 项目：`/Users/xujian/projects/semantica-cnlaw` —— 基于 Semantica 的**可查询、可溯源、可审计的中国法律/专利知识工作环境**。

---

## 1. 项目目标

1. **中国现行有效法律知识库**：法律、行政法规、司法解释、部门规章、宪法（含立项沿革/时效）。
2. **专利知识库**：专利法律、实施细则、司法解释、审查指南、复审无效决定、专利相关判决、经典书籍。

整体：本地模型（数据不出内网、零 API 成本）驱动，可溯源、可审计。

---

## 2. 已完成

### 2.1 环境与基础设施（全部验证通过）

| 项 | 说明 | 验证 |
|---|---|---|
| 隔离环境 `.venv` | Python 3.11.15，`semantica 0.6.6` editable | `import semantica` OK |
| 依赖 | `.[llm-ollama, explorer]`（spacy 3.8 / sentence-transformers 6 / ollama 0.6 / faiss / fastapi / uvicorn） | 均已装；修复了系统环境 spacy/scipy 损坏 |
| Neo4j 持久 | 本机 brew 安装，`bolt://localhost:7687`，认证 `neo4j/neo4j` | `SHOW DATABASES` 显示 neo4j/system 在线 |
| Ollama | `qwen3.8:latest`（27.3B）本地抽取 | 生成中文正常（44s） |
| bge-m3 嵌入 | 官方 `BAAI/bge-m3`（1024 维），本地推理改用 **oMLX `bge-m3-mlx-fp16`** | oMLX `/v1/embeddings` 嵌入中文 OK |
| 中文配置 | `config.yaml`（embedding/kg/graph_store/provenance）+ `.env` | 已加载可用 |
| CLI / MCP | `semantica`（ingest/extract/kg/embed/explorer…）、`semantica-mcp` | `semantica --version` OK |
| Knowledge Explorer | `http://localhost:8001`（8000 让给本机 oMLX），内存图 + 前端已构建 | 首页 200、`/api/health` ok |

**关键命令**：
```bash
cd /Users/xujian/projects/semantica-cnlaw
source bin/activate-env.sh                 # 载入环境变量 + cypher-shell 别名
bash bin/start-neo4j.sh                    # 若 Neo4j 未运行则后台启动
./.venv/bin/semantica --help               # 数据管线/抽取/图谱/导出
set -a && source .env && set +a && ./.venv/bin/uvicorn cnlaw.ingest.explorer_app:app --host 0.0.0.0 --port 8001   # 起 Explorer（预载法律图；必须 source .env，否则 /api/graph/* 全部 503 → 前端"后端不可达"；8000 让给本机 oMLX）
```

**注意**：
- Neo4j 用本机 openjdk25 经 `libexec/bin/neo4j` 直启（brew services 因 openjdk@21 依赖不可靠）；`bin/start-neo4j.sh` 可重启。
- 嵌入离线加载需 `HF_HUB_OFFLINE=1`（已写入 `.env`）；`SEMANTICA_ALLOW_ANONYMOUS=true` 仅限本地开发。
- 向量化与语义检索依赖 **oMLX**（`/Applications/oMLX.app`，常驻 `http://127.0.0.1:8000`，模型 `mlx-community/bge-m3-mlx-fp16`），配置见 `cnlaw/ingest/omlx_client.py`（`CNLAW_OMLX_URL`/`CNLAW_OMLX_MODEL`）。

### 2.2 Explorer 界面简体中文化（已完成并浏览器验证）

引入 **i18next + react-i18next**，默认简体中文、可一键切换英文、偏好持久化（`localStorage['ske-lang']`）。

- 改动的文件：
  - `explorer/src/i18n/index.ts`（初始化/检测/切换）
  - `explorer/src/i18n/locales/zh-CN.json`、`en.json`（双语资源）
  - `explorer/src/main.tsx`（挂载 i18n）
  - `explorer/src/App.tsx`（导航/着陆页/各工作区标题与标签改用 `t()`；左侧栏底部语言切换按钮）
- 已覆盖：应用壳层 + 各工作区标题/标签/导航/着陆页全部中文（已实测切换与 6 个工作区标题）。
- **内部面板细项文案（任务 4，已完成）**：此前「42 个组件的深层文案仍为英文」已补齐——`GraphWorkspace`（`GraphInspectorPanel`/`GraphLoadingOverlay`/`MarkdownContentViewer`/`plugins/*`）、`DiffMergeWorkspace`、`SparqlWorkspace`、`ReasoningWorkspace`、`ImportExportWorkspace`、`DecisionWorkspace`、`EnrichWorkspace`（`EntityResolutionTab`/`RegistryTab`）、`OntologyWorkspace`（`AlignmentsTab`/`OntologyEditor`/`OntologySearch`/`VersionsTab`/`OntologyManager`/`ShaclStudio`/`ProposalReview` 等）、`VocabularyWorkspace`（`ImportDropzone`/`Sidebar`/`PropertyPanel`）、`LineageWorkspace`/`ManageWorkspace` 等内部按钮/标签/空态/错误/加载提示全部转 `t()`。新增 22 个命名空间（`diffMerge`/`sparql`/`reasoning`/`importExport`/`decision`/`entityResolution`/`registry`/`graphInspector`/`markdown`/`graphLoading`/`neighborhood`/`effects`/`legend`/`temporal`/`graphWorkspace`/`vocab`/`alignments`/`ontologyEditor`/`ontologySearch`/`versions`/`lineage`/`manage`），`zh-CN.json`/`en.json` 各新增约 878+ 键。`tsc -b && vite build` 通过；Playwright 实测增强/导入导出、分析/SPARQL、本体中心（含 `注册表/编辑器/版本/对齐/健康/SHACL` 标签栏）等内部面板均已中文显示，英文切换仍正常。**已知残留（有意保留）**：① `GraphWorkspace/GraphCanvas.tsx` 的 `buildEffectAvailability()` 与 `graphAnalytics.ts` 内「效果可用性」状态原因字符串（含模板变量的深度分析子系统）；② 专有名词/格式名（`SPARQL`/`SHACL`/`PROV-O`/`SKOS`/`Turtle`/`RDF/XML` 等）与示例 URL/文件扩展名，按约定不译。

### 2.3 法律知识库引入方案（已确认）

方案文档：`cnlaw/docs/law-import-plan.md`

- **范围（已确认）**：纳入 宪法/宪法相关法/刑法/民法商法/经济法/行政法/社会法/诉讼与非诉讼程序法/民法典/行政法规/司法解释/部门规章/其他；**排除** `地方性法规/`（6845 个）、`案例/`，并甄别剔除 `其他/` 内攻略类非法规文档。规模约 2200 份。
- **时效口径（已确认）**：同法多版本取文件名日期最新为「现行有效」，历史版标「已被修订」并挂 `supersedes`。
- **处理管线**：`parse → normalize → extract → KG(Neo4j) → vector(bge-m3) → provenance → Explorer`。

### 2.4 专利知识库（第四层·第一步：法律/法规/司法解释）—— 已完成

- **范围结论**：全国性专利法律/法规/司法解释（专利法、实施细则、专利代理条例、国防专利条例、最高法系列司法解释）**已随中央法规库入图**，无需重复入库。本步**真正新增**的是 `宝宸知识库_Raw/规章/` 的 **7 部专利部门规章**（专利代理管理办法 / 专利实施强制许可办法 / 专利权质押登记办法 / 专利标识标注办法 / 专利行政执法办法 / 关于规范专利申请行为的若干规定 / 用于专利程序的生物材料保藏办法）+ `法律法规司法解释/` 的 **1 部新司法解释**（最高人民法院关于审理侵害知识产权民事纠纷案件适用惩罚性赔偿的解释，法释〔2026〕7号）。
- **排除**：地方性法规（山东省专利条例、淄博市专利管理若干规定、青岛市专利保护规定、山东省专利纠纷行政裁决和行政调解办法）与技术标准《专利申请号标准》（无 第X条 形态）。
- **domain 知识域**：新增 `law:domain` 属性；专利文件标 `domain='专利'`，`backfill_patent_domain` 按关键词「专利」回填已有专利法律（22 份专利域文档）。
- **解析器增强**：`parse_laws.py` 兼容 `_YYYYMMDD` 文件名日期、扁平文档（INFO END 后无章节标题）正文切分、`**第X条**` 粗体条号、块引用/分隔线清理——并修复了旧逻辑「首个 `##` 标题前条文丢失/整段当沿革」的缺陷。
- **实库与检索**：入库 8 文档 / 229 条；`load_patent` 增量 MERGE（不清库）；向量化新增 228 条（FAISS 56011）；cites 引用边 2953→2973；浏览器验证检索命中新增规章、结果卡显示「专利」domain 标签、图工作区加载 57,828 节点无报错。

### 2.5 专利知识库（第四层·第二步：复审无效决定）—— 已完成

- **范围/口径（已确认）**：接入 `宝宸知识库_Raw/无效复审决定/`（当前 **31,562** 个 md）。**md 为主、JSON 兜底校验**；**现在建轻量 `Patent` 节点**作为与后续「专利判决」的衔接键。复审/无效类型只能从正文判定（文件名不规律：专利号/案件号 `4W5W6W`/`WX`/`+` 复合/`1F`）。
- **领域本体** `cnlaw/ontology/decision.ttl` + `decision-shacl.ttl`：`PatentDecision`（决定号/类型/案件号/决定日/发明名称/IPC/当事人/专利号/申请日/优先权日/公开日/授权公告日/请求日/合议组/法律依据/决定要点/决定结论/技术领域/决定全文…）+ 轻量 `Patent`；对象属性 `involves`(→Patent)、`based_on`(→law:Article)。SHACL：`case_type ∈ {复审,无效,待核验}`、`decision_result` 受控词表、必填 `decision_id`、`domain='专利复审无效'`。
- **解析器** `cnlaw/ingest/parse_decision.py`：兼容 A 表格头/WX/4W/5W、B 专利号（含 `## 附件表格 3`/`## 决定详情`）、C YAML 三格式；脏日期规范化（`20096年412月`→''）；多段归并（按案件号+决定号）；JSON 侧车兜底回填（按 `source_file` 反查，填决定号/结论/决定要点/法律依据，`confidence=json_backfilled`）；修复重复列伪影（`发明创造名称：|发明创造名称：|…` 不再吞标签）；`case_type` 按「文档类型短语首次出现位置」裁决（排除裸「复审决定书」误命中）。
- **解析画像（真实语料冒烟）**：4000 份 0 错误；case_type 无效 3998 / 复审 2；decision_result 分布稳定；约 830/4000 为多段重复（归并）。剩余 ~10% `待核验` 主要是「决定段落缺失/正文被转换截断」所致（已知 docx→md 20,616/31,790 失败），非解析 bug。
- **入库** `cnlaw/ingest/load_decisions_neo4j.py`：`PatentDecision`(按 case_number+decision_id 约束)+`Patent`(按 patent_number 约束)+`involves` 边，增量 MERGE 不清库。**实库结果**：31562 文件 → **29,826 决定 / 26,180 专利 / 28,623 involves**，0 错误。
- **建图** `cnlaw/ingest/decision_citations.py`：复用 `citations.py` 的解析/解析器（`extract_citations`/`_resolve_bare`/`pick_doc_version`/`build_article_index`），抽 `legal_basis`+全文里 `专利法第X条/实施细则第X条` → 连到已在库 **Article** 节点建 `based_on` 边（并清洗「以及/和/款」等前缀噪声）。**实库**：**based_on 67,415 条**（决定→法条，含《专利法》22/46/26 条、《实施细则》20 条等）。
- **向量化** `cnlaw/ingest/vectorize_decisions.py`：**文档级** bge-m3（oMLX 本地 MLX），**独立**索引 `data/vector_store/patent_decisions.faiss` + sidecar `patent_decisions.json`（缓存全文+字段，检索免 Neo4j 回查）。因决定为多页长文，嵌入文本限长 4000 字符 + `sub_batch=2`/重试 5 次规避 oMLX Metal 溢出；断点续跑。全量已嵌入 **29,825 份**（2026-08-26 夜间续跑完成）；侧车字段覆盖 `legal_basis` 98%、`decision_result` 100%、`case_type` 100%、`decision_points` 约 51%、`ipc` 约一半，缺失如实标注。
- **Explorer/检索**：`explorer_graph.py` 加载 `PatentDecision`(`dec:…`)/`Patent`(`patent:…`) 及 `involves`/`based_on` 边；`search_service` 同时加载条文+决定两套后端，新增 `/search/decisions`；`cnlaw_api`/`semantic_search` 新增 `/api/cnlaw/search/decisions`；前端 `LawSearchWorkspace` 改为「条文 / 复审/无效决定」双模式（i18n 双语）。**实库图**：node_count **115,067**（PatentDecision 29,826 / Patent 26,180 / Article 57,204 / LegalDocument 1,843），edge_count **160,024**（based_on 67,415 / involves 28,623 / has_article / cites / belongs_to_category / supersedes）。
- **浏览器验证**：条文/决定双模式端到端——切换「决定」搜「区别技术特征 具备创造性」命中决定卡片（决定号/案件号/专利号/结论 复审撤销驳回、无效全部无效/维持有效/决定要点/溯源路径）；切回「条文」搜「侵犯专利权 帮助侵权」命中《专利法》现行有效条文+溯源；图工作区加载「知识图谱」画布无报错。**风险**：115k 节点画布渲染较重，截屏偶发超时（非功能回归）。

---

### 2.6 专利知识库（第四层·第三步：专利判决）—— 已完成

- **范围/口径（已确认）**：接入 `专利判决/`（6,301 md）+ `指导性专利判决文书_md/`（885 md），按案号去重合并。**全收并打「案由」标签**（民事/行政，含专利/商标/不正当竞争，不丢案例）；无 JSON 侧车（纯 md 解析）。复用既有 `Patent` 节点作为与复审无效决定的衔接键；`involves` 连到同一 `patent_number`。
- **领域本体** `cnlaw/ontology/judgment.ttl` + `judgment-shacl.ttl`：`jg:PatentJudgment`（判决标识/案号/案件类型/案由/审理法院/裁判日期/发明名称/专利权人/原告/被告/合议庭/法律依据/裁判要点/判决结果/权利要求/说理/专利号/判决全文…），`jg:Patent` = `dec:Patent`（`owl:equivalentClass`）；对象属性 `involves`(→Patent)、`based_on`(→law:Article)。SHACL：`case_type ∈ {民事,行政,刑事,待核验}`、必填 `judgment_id`、`domain='专利判决'`、`involves` 指向 `Patent`。
- **解析器** `cnlaw/ingest/parse_judgment.py`：兼容两种元数据布局——`专利判决/` 的 `## 案件信息`（`**字段**: 值`）+ `## 判决书正文`，与 `指导性` 的换行分隔 `label\n：\nvalue`；案号规范化（全半角括号统一、去空格）；案由去 `★` 噪声；抽取审理法院/案号/裁判日期/案由/原告/被告/发明名称/专利权人(`…的专利权人`)/涉及专利号(`ZL…`+`专利号：`)/法律依据(`依照《…》…之规定`)/判决结果(`判决如下`/`驳回上诉，维持原判`)/`本院认为`说理/裁判要点(`争议焦点`)/合议庭(`审判长/审判员：`)。按规范化案号归并多段文件。
- **解析画像（真实语料全量）**：**7,186 文件 → 去重 5,969 判决**，0 错误（解析约 17s）；case_type 民事多数 + 行政；2,206 涉及专利 / 3,038 `involves` 边候选。
- **入库** `cnlaw/ingest/load_judgments_neo4j.py`：`PatentJudgment`(按 case_number+judgment_id 约束)+ `Patent`(按 patent_number 约束，仅非空才写以便不覆盖复审无效写的 domain)+ `involves` 边，增量 MERGE。**实库结果**：7186 文件 → **5,969 判决 / 2,206 专利 / 3,038 involves**，0 错误（约 18s）。
- **建图** `cnlaw/ingest/judgment_citations.py`：复用 `citations.py`；抽 `legal_basis`+全文 `《…》第X条` → 连 Article 建 `based_on` 边。**实库**：**based_on 19,268 条**（判决→法条。注：`《法》第十一条、第五十九条`这类「一条内多款」共享抽取器只取首个条款，属既有 `citations` 局限）。
- **向量化** `cnlaw/ingest/vectorize_judgments.py`：文档级 bge-m3，独立索引 `data/vector_store/patent_judgments.faiss` + sidecar `patent_judgments.json`；限长 4000 字符 + `sub_batch=2`/重试 5 次。已全量嵌入 **5,969 份**（2026-08-26 夜间续跑完成）；侧车字段覆盖 `legal_basis`（`--backfill-fields` 回填后 87%）、`case_type` 100%、`decision_result` 98%、`court` 约 18%，缺失如实标注。
- **Explorer/检索**：`explorer_graph.py` 增补 `PatentJudgment`(`jug:…`)/`involves`/`based_on`；`search_service` 加载条文+决定+判决三套后端，新增 `/search/judgments` 与 `/health` 的 `judgments_ready`；`cnlaw_api`/`semantic_search` 新增 `/api/cnlaw/search/judgments`；前端 `LawSearchWorkspace` 改为「条文 / 复审/无效决定 / 专利判决」三模式（i18n 双语），`JudgmentCard` 展示案号/法院/专利号/案由/判决结果/溯源。
- **浏览器验证**：三模式按钮均渲染；切「专利判决」搜「等同侵权 全面覆盖原则」命中判决卡片；切回「条文/复审」模式占位符与结果正确，无回归。
- **一键脚本** `bin/build_patent_judgments.sh`：入库 → based_on → 全量向量化 →（自动重启检索服务并轮询 `judgments_ready`），幂等可重复/断点跑；支持 `--limit`/`--clear`/`--no-restart`。夜间全量直接跑该脚本即可。

---

### 2.7 专利知识库（第四层·IPC 国际专利分类表 + 与复审/无效决定关联）—— 已完成

- **范围/口径（已确认）**：接入 `宝宸知识库_Raw/IPC分类表/extracted_text/` 的 **2026.01 版 8 部 txt**（A-H 部）。**代码本身即编码层级**（`A→A01→A01B→A01B1/00→A01B1/02`），父关系与聚合均由 code 推导，不依赖易错的 PDF 版面。**已知局限**：部分类/小类标题被注记/索引残片污染或缺失（PDF 抽取所致），关联以 code 为权威、标题尽力清洗。
- **领域本体** `cnlaw/ontology/ipc.ttl` + `ipc-shacl.ttl`：`ipc:IpcNode`（`code/title/level/version`）+ 对象属性 `ipc:parent`（层级树）、`ipc:classified_in`（domain=决定/专利并集 → IpcNode）。SHACL：`level ∈ {section,class,subclass,group,subgroup}`、`code` 必填且形如 `A/A01/A01B/A01B1/00`、`classified_in` 目标必为 IpcNode。
- **解析器** `cnlaw/ingest/parse_ipc.py`：按「code 位于第 0 列」识别条目（缩进续行跳过），去页眉/页脚；层级由 code 结构推导；标题去版本标记/前导点；部标题从 `X部——` 行或标准 8 部兜底；`build_ipc_tree` 由 code + 小组前导点推导 `parent`（subgroup→最近上位小组/`/00` 大组→subclass→class→section）。`normalize_ipc_codes` 清洗决定脏字段（版本/空格/多值），`resolve_ipc` 逐级回退（完整码→`/00` 大组→subclass→class→section）。
- **入库** `cnlaw/ingest/load_ipc_neo4j.py`：`IpcNode`(按 `code` 约束)+`parent` 边，增量 MERGE 不清库。**实库结果**：**79,972 节点**（部 8 / 类 132 / 小类 655 / 大组 7,667 / 小组 71,510）+ **79,959 parent 边**。
- **建边** `cnlaw/ingest/ipc_links.py`：读取 `PatentDecision.ipc`/`Patent.ipc` → 归一化 → resolve → 建 `classified_in` 边（决定/专利→最具体 IPC 节点）。**实库**：**decision_classified_in 24,653 / patent_classified_in 21,810**（共 46,463 条）。约 51% 决定能解析出 IPC（数据本身局限），聚合适用 code 前缀（`A01B*` = 小类 A01B 全部后代）。
- **Explorer/检索**：`explorer_graph.py` 画布仅纳入 `section/class/subclass` 三层（约 600 节点）+ `parent` 边 + `classified_in`（决定/专利连到其**小类**节点，避免 77k 节点拖垮渲染；全量留在 Neo4j 供精确查询）；新增 `ipc_api.py`（Neo4j 直查，`/api/cnlaw/ipc/sections`、`/tree?parent=`、`/{code}/decisions`）并挂载 `explorer_app`；`vectorize_decisions`/`search_worker`/`cnlaw_api`/`search_service` 均在决定命中带 `ipc` 字段；前端 `LawSearchWorkspace` 改 4 模式（条文/复审无效决定/专利判决/IPC 分类），新增 `IpcBrowser` 树（部→类→小类→组/小组懒加载，点节点列出其下决定），`DecisionCard` 显 IPC 标签。
- **一键脚本** `bin/build_ipc.sh`：入库 → classified_in 边（幂等可重复；IPC 不向量化，分类 API 运行时直查 Neo4j 无需重启检索服务；可选 `--restart-explorer` 重载画布）。
- **测试**：`test_parse_ipc` / `test_load_ipc_plan` / `test_ipc_links` / `test_ipc_shacl` 共 **16 项**；`cnlaw/tests` 全量 **131 项通过**。浏览器验证条文/决定/判决三模式无回归，IPC 分类浏览器端到端命中。

---

### 2.8 专利知识库（经典书籍·《以案说法》）—— 已完成

- **范围/口径（已确认）**：本期经典书籍仅引入 `以案说法：专利复审、无效典型案例指引`（国家知识产权局专利复审委员会 编著，知识产权出版社 2018，460 千字）；数据源为已提取的 `宝宸知识库_Raw/书籍/extracted/第X章-*.txt`（12 章；`全书-full.txt` 不计入）。
- **建模（复用 guide 管线）**：每章 → `LegalDocument`（`domain='专利'`、`category='书籍'`、`legal_level='书籍'`、`status='现行有效'`、`promulgated_date=2018-09-01`），每个编号要点（`1`/`1.1`/`1.1.1`/`4.4.1`）→ `LawArticle`（`kind='book_section'`，`number`=节路径，`level`/`parent_number`/`part`/`chapter` 层级元数据），章引言成 `0` 号 `introduction` 节点。复用 `law.ttl`/`law-shacl.ttl`，不新增本体。
- **解析器** `parse_book.py`：OCR 数字归一化（`l/I`→`1`、全角点/点间空格归一：`4. 4. l 现有设计状况的考量`→`4.4.1`，`3. 3. l. 1`→`3.3.1.1`）；标题判定拒绝句读/顿号/ASCII 混入（防正文误判标题）；过滤页眉/页码/目录噪声。**12 章 / 351 节**；`book_section` 图内 346（5 处同章重复条号在 MERGE 合并，无丢文本）。
- **入库** `load_book.py`：复用 `build_import_plan`/`build_article_plan`/`apply_*`，增量 MERGE 不清库。**实库**：12 章 / 358 条文（346 section+12 introduction）/ `LegalCategory '书籍'` + `belongs_to_category` 12 边；SHACL 必填属性（status/promulgated_date/legal_level/has_article）核验通过。
- **向量化**：书籍条文随 `vectorize_articles --status 现行有效` 自动入 law_articles 索引，`done 57204→57562`（+358）。
- **检索/前端**：`search_worker`/`search_service:SemHit`/`cnlaw_api:LawHit` 三处透传 `category`；前端 `LawCard` 在 `category` 非空且≠`domain` 时显示分类标签（书籍/审查指南）。《以案说法》检索命中（`full_name='《以案说法…》章 节号'`、`cat='书籍'`、`dom='专利'`）；已重启检索服务与 Explorer。
- **测试**：`test_parse_book`（9）+ `test_load_book_plan`（2）= **11 项**；`cnlaw/tests` 全量 **142 项通过**。图统计 **124,074 节点 / 217,496 边**。浏览器替代验证（curl 前端真实 API 链路）命中书籍条文并返回 `category=书籍`；因无浏览器自动化工具，未做真实 DOM 渲染/交互验证。

---

### 2.9 专利知识库（第四层·审查指南）—— 已完成

- **范围/口径**：接入 `专利审查指南/`（2023 版全文），经 `prepare_guide_corpus.py` 归一化为逐章 markdown（`部分→章→节→小节`），`parse_guide.py` 将每个编号章节（`1`/`2.1`/`3.1.2`）解析为 `LawArticle`（`kind='guideline_section'`），章级引言成 `0` 号 `introduction` 节点；另解析 `修改对照表.md`（2023→2026，`kind='amendment'`）为独立可检索文档。`load_guide.py` 复用 `build_import_plan`/`build_article_plan`/`apply_*` 增量 MERGE。
- **category 标记（任务 6）**：指南文档在入库时即带 `category='审查指南'`、`domain='专利'`，反映为 `LegalDocument -[:belongs_to_category]-> LegalCategory('审查指南')` 边；实库 `LegalCategory '审查指南'` 存在，**39 篇指南文档 / 1193 条指南条文**全部挂此边。此前的观察「指南文档 category 为空」是**检索链路未透传 `category`** 所致（`search_worker` 命中字典在《以案说法》阶段才补上 `entry.get("category")`），并非图上缺失。核查证明：`vectorize_articles` 写入 sidecar 的指南条目含 `category='审查指南'`；`POST /search`（8100）与 `GET /api/cnlaw/search`（8001）对「专利审查指南 新颖性 单独对比」均返回 `category='审查指南'`；前端 `LawCard` 的 `{category && category !== domain && …}` 芯片在 category≠domain 时显示「审查指南」标签。**前端已可按类/标签区分指南**，无需额外缺失修复。
- **检索验证**：指南条文已入 law_articles 索引（随 `vectorize_articles --status 现行有效` 自动嵌入），语义检索命中《专利审查指南》「新颖性」「创造性」等章节并返回 `full_name='专利审查指南 第…部分…·第…章 …'`、`cat='审查指南'`、`dom='专利'`。

---

### 2.10 专利模式·CNLaw 底座接入 + 图谱/案件扩展（阶段 A–D）—— 已完成

2026-08-26 为 DeepSeek Harness「专利模式」接入 cnlaw 权威法律底座的扩展（同期设计/交接文档：`cnlaw/docs/patent-mode-wiring-design.md`、`patent-mode-integration-handover.md`）。cnlaw 侧全部**增量新增、不清库**；shipped `patent` 预设本体未动，仅新增用户级副本 `专利模式·CNLaw 底座`（`~/.dsh/.agent-presets/patent-cnlaw/`）。

- **权威度分层（A）**：`search_worker._authority_tier` 将检索来源分层（tier 1 法条/法规/解释/规章 → 2 审查指南 → 3 判例(决定+判决) → 4 书籍），`_rank_hits` 改按 `(tier, 现行有效, −score)` 排序，`/search` 命中带 `tier`——修正「分数高的书籍/指南压过法规」的权威次序错误。
- **判例定向检索（B）**：`/search/decisions|judgments` 与 `:8001/api/cnlaw/search/*` 新增可选过滤 `ground`（法条子串，中/阿数字自动归一）/`ipc`（分类前缀，仅决定）/`result`/`case_type`，命中带 `legal_basis`；`vectorize_judgments` 侧车补存 `legal_basis`/`decision_points` + `--backfill-fields`（离线回填判决 legal_basis 至 87%）。过滤逻辑集中在 `_field_filter`（纯函数），带过滤时 FAISS 窗口放宽至 k×10。
- **图谱精确导航（C）**：新增 `graph_api.py`（`graph_router`，挂 8001）：`/graph/ground`（按 `based_on` 由法条找决定+判决；可加 `ipc` 限定子树、`law` 消歧）、`/graph/patent`（按 `involves` 由专利号追踪其决定+判决+IPC）。`cn_num.py` 提供中/阿数字归一（`extract_article_number`/`arabic_to_cn`/`cn_numerals_to_arabic`）。**本轮为 ground 增 `offset` 分页**：`RETURN DISTINCT … ORDER BY case_number, id SKIP $offset LIMIT $k`，响应新增 `total_decisions`/`total_judgments`（DISTINCT 计数）/`has_more`，突破「每 kind LIMIT 100/200」上限——实测 `专利法第22条第3款` 下决定 **16,384** / 判决 **1,525**，翻页稳定无重复。
- **案件级决策链（D）**：新增 `case_api.py`（`case_router`，挂 8001）：`POST /case/{id}/decision`（自动分配 `step` + `:next` 因果链，首条自动建 Case）、`GET /case/{id}`、`GET /case/{id}/chain`。模型 `Case {case_id,title,status}`→`:has_decision`→`CaseDecision {step,category,scenario,reasoning,outcome,confidence,decision_maker,entities[],source_paths[]}`→`:next`；修复 title 被后续 step 空串覆盖。`vectorize_cases.py` 将 `scenario+reasoning` 向量化到独立 FAISS，供 `/case/similar` 按相似场景检索历史决策（复用闭环）。
- **工具化（D″）**：`cnlaw_mcp.py` + `cnlaw_mcp_launcher.py` 用 pypi `mcp`（2.x，`MCPServer`）暴露 6 个原生工具（`cnlaw_graph_ground/patent`、`cnlaw_case_record/get/chain/similar`），代理到 :8001（`httpx`，`trust_env=False` 规避宿主代理把 localhost 路由 502）；launcher 强制 pypi SDK，规避项目根自带同名 `mcp/` 遮蔽。DSH 预设追加 `mcp-cnlaw` 行，会话获得 `mcp__cnlaw__*` 工具。
- **向量化全量收口**：决定侧车 29,825 / 判决侧车 5,969 均已全量嵌入（2026-08-26 夜间续跑完成）。
- **测试**：`cnlaw/tests` 现全套 **169 项通过**（新增 `test_graph_api.py` 5、`test_cn_num.py` 5、`test_precedent_filter.py` 9 项回归）。

---

## 3. 数据源

- `Laws-1.0.0`：中央法规库（md 正文 + `db.sqlite3` 分类表）。**本方案目标数据**。来源为 flk.npc.gov.cn 下载的 docx（`名称_YYYYMMDD.docx`），经库内 `scripts/parsers/word.py` 转 md + 分类 + 定期自动更新（更新报告 2026-01-18，总数 7170）。docx 原始档（现有 23 个，集中于专利/商标目录）**仅作溯源存档、不进入解析管线**（2026-08-25 确认）。
- `/Users/xujian/Downloads/专利无效数据/202601~202604.zip`：专利无效数据压缩包（**待处理**；`dsh-synapse-main/` 疑似误放，可忽略）。
- `/Users/xujian/projects/宝宸知识库_Raw/`：`无效复审决定/`（9.7 万 md/json）、`法律法规司法解释/`、`专利审查指南/`、`商标法律法规数据库/`、`书籍/`、`个人笔记/` 等（留档，非法律库范围）。

---

## 4. 里程碑状态

### M0：法律知识库引入（解析层）—— 已完成

- [x] 领域本体 `cnlaw/ontology/law.ttl`：实体 `LegalDocument/Article/LegalCategory/EnactingBody/LegalLevel`；对象属性 `belongs_to_category / has_article / amended_by / supersedes / based_on`；数据属性 `name/full_name/promulgated_date/amended_date/legal_level/status/document_number/effective_date/number`。5 类 + 5 对象属性 + 9 数据属性，108 三元组，rdflib 校验通过。
- [x] 解析器 `cnlaw/ingest/parse_laws.py`：读 md → 法律全名/部门/颁布与历次修正日期/效力层级/条文（`第X条`，含「之N」子条），过滤 Obsidian 标记与 `<!-- INFO END -->`；兼容无日期/带日期两种 md 结构。
- [x] 地方法规排除规则 `cnlaw/ingest/exclusion.py`：目录级排除 `地方性法规/`、`_index.md` 索引文件、攻略类文档；标题否定规则把疑似地方性法规标记为 `likely_local` 待人工复核（不硬删）。
- [x] SHACL 约束 `cnlaw/ontology/law-shacl.ttl` + 校验入口 `cnlaw/ingest/law_shacl.py`：`status` 枚举、发布日期/效力层级必填、条文必有条号、`has_article` 指向 Article；经 PySHACL（依赖 `semantica[shacl]`，已安装）校验，可拦截非法状态/缺日期/缺条号。
- [x] 测试 `cnlaw/tests/`（test_parse_laws.py / test_exclusion.py / test_shacl.py）共 **18 项全部通过**；真实语料端到端冒烟（解析→RDF→SHACL）通过。

**M0 数据画像（真实语料冒烟）**：

- 纳入部门合计：保留 **1966 份** + 待复核 **172 份**（13 个索引 + 158 个疑似地方性法规 + 1 个攻略），共 2138 个 `.md` 文件，与方案「约 2200 份」基本吻合。
- **217 份「待人工复核」收尾（任务 7，已完成）**：M0 曾把 203 个疑似地方性法规标记待复核；复核发现 `is_local_regulation` 正则**过宽误伤**——凡标题含「市/县/区/地区」且以条例/办法/规定结尾者皆命中，把一批**真正的全国性法规**（如 `城市公共交通条例`、`行政区划管理条例`、`风景名胜区条例`、`人力资源市场暂行条例`、`中华人民共和国市场主体登记管理条例`、`最高人民法院关于审理证券市场虚假陈述侵权民事赔偿案件的若干规定`、`国务院关于股份有限公司境内上市外资股的规定`、`全国人大常委会关于在沿海港口城市设立海事法院的决定` 等）误判为地方性法规而排除出库。已修复 `exclusion.py`：新增「国家权力机关/国家机关名称开头（全国/国务院/最高人民法院/最高人民检察院/中华人民共和国/中国人民解放军/中央）」与「通用政策领域名词开头（城市/行政区划/行政区域/风景名胜区/蓄滞洪区/人力资源市场/森林和野生动物/矿产资源/自然保护区/保税区/进出口/民族工作）」两类豁免，仅保留具体地名为主语者（`三都水族自治县都柳江渔业条例`、`新疆/内蒙古/广西自治区条例`、`中国（上海）自由贸易试验区条例`、`深圳经济特区…` 等）判为地方性法规。修复后保留 1921→**1966**、疑似地方性法规 203→**158**，恢复 **45 份**全国性法规；`test_exclusion.py` 增补回归用例（6 项）。已重跑 `load_laws_neo4j` 增量入库（MERGE 不清库），恢复条文已向量化入 law_articles 索引（done **65542→70057**，新增 **4515** 条；为规避 oMLX 对超长条文的 Metal 溢出/断连，`vectorize_articles` 嵌入时对文本**限长 4000 字符**，与决定/判决管线一致，sidecar `meta` 仍存全文供显示；并修复了 `is_local_regulation` 误伤导致的全国性法规缺失）。注：`中国（…）自由贸易试验区条例` 系省级人大常委会制定，仍属地方性法规，保留排除。
- 目录级排除：`地方性法规/` 6845 个、`案例/` 57 个。
- 关键发现：`行政法规/` 目录混入 **191 个地方性法规**（自治县/市条例等），标题核验规则已命中；`其他/` 含 1 个攻略类文档被剔除。
- 《刑法》两版本解析一致：1979-07-01 通过 + 14 次修正日期，505 条（452 个母条 + 53 个之N 子条），唯一显示条号 505。
- 观察（待 M1 处理）：部门分类不唯一——如 `专利法(2020-10-17)` 同时出现在 `行政法/` 与 `民法商法/`。入库前需按 `full_name`（+文件名日期）去重/统一归属，避免同一法律重复入图。

**运行方式**：
```bash
# SHACL 测试依赖 semantica + pyshacl，需用 .venv 统一运行
./.venv/bin/pip install "semantica[shacl]" "pytest>=7.1.0"   # 若未装（含 pyshacl）
./.venv/bin/python -m pytest cnlaw/tests -v
```

### M1：元数据入库（法律级 L0）—— 已完成

- [x] `cnlaw/ingest/load_laws_neo4j.py`：`scan_and_parse`（复用 M0 解析器+排除规则）→ `build_import_plan`（按 full_name+source_date 去重、`compute_effective_status` 版本归并、类别归属、supersedes 配对）→ `apply_import_plan`（UNWIND 批量 Cypher 写入）。
- [x] 依赖：`neo4j>=5.0.0`（semantica 的 graph-neo4j extra）。
- [x] CLI：`./.venv/bin/python -m cnlaw.ingest.load_laws_neo4j [--clear|--dry-run]`。
- [x] 测试 `cnlaw/tests/test_load_plan.py`（5 项）——去重/状态/类别/版本关系纯逻辑，不连库。

**M1 实库结果**（Neo4j @ bolt://localhost:7687）：
- LegalDocument **1796** 节点、LegalCategory **12**、belongs_to_category **1876**、supersedes **138**。
- status 分布：现行有效 **1658** / 已被修订 **138**（无待核验）。
- 分类冗余：**79** 个法律一法多类别（如专利法同挂 行政法/民法商法），保留全部类别以溯源、不丢信息。
- supersedes 样例：立法法 / 村民委员会组织法 / 监察法 由历史版指向现行版。

**运行命令**：
```bash
./.venv/bin/python -m cnlaw.ingest.load_laws_neo4j --dry-run    # 只看计划统计
./.venv/bin/python -m cnlaw.ingest.load_laws_neo4j --clear      # 清空 cnlaw 子图并写入
```

### M2：条文入库（Article 节点 + has_article 建图）—— 已完成

- [x] `build_article_plan`（按 full_name+source_date 去重后拉平条文，含条号/`order`）→ `apply_import_articles`（UNWIND 批量 MERGE Article + has_article）。Article 唯一约束 `(full_name, source_date, number)`。
- [x] CLI 默认同时写 L0 与条文；`--no-articles` 仅 L0；`--clear` 清理 Article 子图。
- [x] 测试 `test_load_plan.py` 新增条文去重测试，`cnlaw/tests` 共 **24 项全部通过**。

**M2 实库结果**：
- Article **55783** 节点、has_article **55783** 关系，**0** 孤立节点（每条都挂在对应 LegalDocument 下）。
- 抽查 刑法(2020-12-26) 现行版 **505** 条，条号/正文正确。
- 条文按法律版本全量入库：现行有效 1658 + 已被修订 138（所有版本条文均可溯源）。

### M3：条文向量化 —— 已完成（oMLX 本地 MLX 推理）

- [x] 嵌入后端切换：新增 `cnlaw/ingest/omlx_client.py`（`OmlxEmbedder`，HTTP 客户端调 oMLX `/v1/embeddings`），`vectorize_articles.py`/`search_worker.py` 改用 oMLX；移除 fastembed/onnx 的 e5 前缀常量。**bge-m3 无需 query/passage 前缀**。
- [x] 依赖：oMLX App（`/Applications/oMLX.app`，`serv` 常驻 `127.0.0.1:8000`）+ 模型 `mlx-community/bge-m3-mlx-fp16`（1024 维，MLX/Metal GPU）；FAISS。
- [x] 测试 `test_vectorize.py`（7 项）——id 生成/分批/去重/元数据/续跑读档；`cnlaw/tests` 共 **31 项通过**。
- [x] 全量向量化完成：现行有效 **48295** 条全部写入 FAISS（`ntotal=48295`，sidecar `ids=done=48295` 对齐），分批 + 断点续跑；落盘 `data/vector_store/law_articles.faiss`（198MB）+ `data/vector_meta/law_articles.json`（7.1MB）。
- [x] 修复 FAISSIndex.load 不恢复 vector_ids 的 bug：`build_faiss_store` 从 sidecar 还原 `vector_ids`，避免续跑后 ids 错位导致查询越界。
- [x] sidecar 缓存条文全文（`meta` 映射）+ `--backfill` 回填：检索命中直接读 sidecar 的 `text`，**省掉每条命中的 Neo4j 回查**，查询链路不再依赖 Neo4j。
- 提速备注：oMLX 单次前向曾出现 Metal 显存溢出（长文堆叠），已把 `sub_batch` 降到 8 并加重试；可进一步换 `bge-m3-mlx-8bit`（同为 1024 维、0.59GB）提速。
### M4：验证 + Explorer 加载 —— 已完成（oMLX 端到端）

- [x] 图加载：`cnlaw/ingest/explorer_graph.py`（从 Neo4j 直查，构造可读 id 的 entities/relationships → `ContextGraph.build_from_entities_and_relationships`）+ `cnlaw/ingest/explorer_app.py`（`create_app(session=GraphSession(law_graph))`）。启动命令改用 **`cnlaw.ingest.explorer_app:app`**（仍须 `source .env`）。
- [x] 实测：`/api/graph/stats` 返回 `node_count=57591`（LegalDocument 1796 / LegalCategory 12 / Article 55783）、`edge_count=57797`（has_article 55783 / belongs_to_category 1876 / supersedes 138）；图构建约 **4.2s**。
- [x] 浏览器视觉验证：系统状态卡片显示"知识节点 **57,591** / 已映射关系 **57,797**"；"知识浏览"工作区正常加载 nodes→relationships，canvas 渲染（`canvas=1`）。
- [x] 向量检索接入（前端 `LawSearchWorkspace` + `npm run build`）—— **oMLX 方案解决段错误**：原 torch 2.13 编码非确定性段错误（`/search` 与批量重建 exit 139）靠换 oMLX（MLX/Metal，不依赖 torch）规避。`search_service`/`semantic_search`/`explorer_app` 的 `/api/cnlaw/search` 链路打通；前端 `explorer/src/workspaces/LawSearchWorkspace/` 读取 `data.results`（full_name/number/text/score/status/source_path），卡片底部展示「溯源：源路径 · 日期 · 状态」。
- [x] 多查询回归：12 法律域 × 3 = **34/36（94%）** Top-3 命中（如 专利法22条「创造性」、商标法34条「驳回复审救济」、工伤保险条例14条「工伤认定」、专利法42条「保护期限二十年」）。
- **[x] 画布渲染性能重测（任务 5，已完成并确认瓶颈）**：现图已达 **124,074 节点 / 217,496 边**，远超 M4 时 5.7 万边。实测（Playwright + headless Chromium）：图工作区在前端「关系构建」阶段（STAGE 3/6）以约 **200 边/秒**线性加载，**7 分钟后仅到 88,000/217,496（40%）**，始终未进入 LAYOUT 交互阶段；按此速率完整加载边需约 18 分钟，**画布无法在有界时间内可交互渲染**。结论：当前画布管线对 21.7 万边不可扩展，属实测回归瓶颈；节点全部 124,074 已就绪，瓶颈集中在**关系（边）的客户端构建/摄入**（纯 JS/数据任务，与 WebGL 后端无关）。建议：画布端对边做分层/抽样或仅加载当前视口邻居（参考 IPC 分类已仅暴露三层的小图策略），全量边留在 Neo4j 供精确查询；或在 `explorer_graph.py` 侧对 `cites`/`based_on`/`involves` 边按需勾选、限制每条文档/决定展示边数。

**运行命令**：
```bash
./.venv/bin/python -m cnlaw.ingest.vectorize_articles --dry-run   # 统计待向量化条数
./.venv/bin/python -m cnlaw.ingest.vectorize_articles            # 全量（断点续跑，可中断重启）
./.venv/bin/python -m cnlaw.ingest.vectorize_articles --all-versions  # 含历史版
```

---

## 5. 决策记录

| 日期 | 决策 |
|---|---|
| 2026-08-25 | LLM 用本地 Ollama `qwen3.8:latest`（数据不出内网）；嵌入用官方 `BAAI/bge-m3`（1024 维）；图库用本机 Neo4j；同时起 Explorer。 |
| 2026-08-25 | Explorer 界面引入 i18next + react-i18next，默认简体中文可切换英文。 |
| 2026-08-25 | 法律库纳入中央法规（含宪法/司法解释/部门规章/其他），排除地方性法规与案例；时效「最新日期=现行有效」。 |
| 2026-08-25 | 无日期版本时效口径：无日期版视为「现行有效」（其内容与最新日期版一致）；历史日期版标「已被修订」。 |
| 2026-08-25 | 数据源与格式口径：以 `Laws-1.0.0`（md）为主线；其源头即 flk.npc.gov.cn 下载的 docx（经 `word.py` 转换，权威性已满足），故 docx **仅作原始溯源存档、不解析**，不重开 docx 采集/解析管线。 |
| 2026-08-25 | 向量化/检索切到 **oMLX 本地 MLX 推理**：`bge-m3-mlx-fp16`（1024 维）经 oMLX `/v1/embeddings` 提供嵌入，解决 torch 2.13 编码段错误；LLM 仍用本地 Ollama。oMLX 常驻 8000，Explorer 用 8001。 |
| 2026-08-25 | 检索性能：sidecar `meta` 缓存条文全文 `text`，查询命中从 sidecar 反查，免逐条 Neo4j 回查；新增 `--backfill` 回填存量数据，`bin/cnlaw_regression.py` 可重复回归（含边界用例）。 |
| 2026-08-25 | 专利判决（第四层·第三步）：接入 `专利判决/` + `指导性专利判决文书_md/`（7,186 md）；**合并去重**（按规范化案号，得 5,969 判决）；**全收并打案由标签**（民事/行政，含专利/商标/不正当竞争，不丢案例）。新增 `judgment.ttl`/`judgment-shacl.ttl`（`PatentJudgment`+`jg:Patent`=`dec:Patent`）；`parse_judgment.py` 兼容 `## 案件信息` 与换行分隔两种元数据布局，复用既有 `Patent` 节点作衔接键（`involves`→同一 `patent_number`）。入库 5,969 判决/2,206 专利/3,038 involves，`based_on` 19,268 条；文档级 bge-m3 独立 FAISS（`patent_judgments.faiss`，限长 4000 字符 + `sub_batch=2`）；`search_service`/`cnlaw_api`/前端 `LawSearchWorkspace` 三模式（条文/复审无效决定/专利判决），浏览器端到端验证通过（全量向量化已于 2026-08-26 夜间续跑完成）。 |
| 2026-08-25 | 溯源（provenance）：把 `LegalDocument.path`（源文件完整路径）写入 Neo4j 并随 sidecar `meta` 缓存，检索命中返回 `source_path`，Explorer 溯源行展示「源路径 · 日期 · 状态」，实现逐条可审计；`--backfill-path` 增量补写存量，不重跑向量化/清库。 |
| 2026-08-25 | 法条引用关系：从条文正文提取「本法第X条」（同文档）与「《某法》第X条」（跨文档）引用，经中文数字转阿拉伯 + 简称→全称匹配（唯一子串）+ 现行版选择解析，建 Article→Article `cites` 边（2953 条）；`cnlaw/ingest/citations.py` 为纯函数可测，Explorer 加载 `cites` 类型边（图边 57,797→60,750）。 |
| 2026-08-25 | 失效法律追踪：把「已被修订」7488 条也 `--status 已被修订` 增量向量化进检索池（FAISS 55783 条，sidecar `status` 如实标记）；查询命中「已被修订」时 `score×0.5` 降权，并按「现行有效优先（分组）+ 分数降序」排序（`_rank_hits`），status 明确返回供前端标记——现行有效永远排在被修订前。 |
| 2026-08-25 | 专利知识库（第四层·第一步）：引入 `domain` 属性区分知识域，专利文件标 `domain='专利'`（含回填已有专利法律）。全国性专利法律/法规/司法解释已随中央法规库入图（按 `full_name@source_date` 归并不重复建点）；本步真正新增的是 7 部专利部门规章（代理管理/强制许可/质押登记/标识标注/行政执法/规范申请行为/生物材料保藏）+ 1 部 2026 惩罚性赔偿司法解释（法释〔2026〕7号）；排除地方性法规（鲁/鲁/淄/青）与技术标准《专利申请号标准》。 |
| 2026-08-25 | 解析器增强（支撑专利语料）：`parse_laws.py` 兼容 `_YYYYMMDD` 文件名日期、扁平文档（INFO END 后无章节标题）正文切分、`**第X条**` 粗体条号、块引用/分隔线清理；`load_patent.py` 增量入库（MERGE 不清库）+ `backfill_patent_domain` 关键词「专利」回填；`law.ttl` 新增 `law:domain`；侧车/检索/Explorer 元数据透传 `domain`，前端检索卡右上角展示 domain 标签。 |
| 2026-08-25 | IPC 国际专利分类表（第四层·关联）：接入 2026.01 版 8 部分类表（79,972 节点）；**code 即层级**，父关系/聚合由 code 推导（前缀匹配），规避 PDF 版面噪声；新增 `ipc.ttl`/`ipc-shacl.ttl`（`IpcNode`+`parent`+`classified_in`）；`parse_ipc.py`/`load_ipc_neo4j.py`/`ipc_links.py` 建决定/专利→IPC 边（24,653/21,810）；`ipc_api.py` 提供分类树与"某分类下决定"检索；`explorer_graph.py` 画布仅纳入部/类/小类三层；前端 `LawSearchWorkspace` 增 IPC 分类浏览器，`DecisionCard` 显 IPC 标签。 |
| 2026-08-25 | 专利复审无效决定（第四层·第二步）：接入 `无效复审决定/`（31,562 md）；**md 为主、JSON 侧车兜底校验**；**建轻量 `Patent` 节点**作为与后续「专利判决」的衔接键；新增 `decision.ttl`/`decision-shacl.ttl`（`PatentDecision`+`Patent`，`involves`→Patent、`based_on`→law:Article）。复审/无效类型从正文判定（非文件名）；`parse_decision.py` 兼容 A/B/C 三格式、脏日期规范化、多段归并、JSON 回填；入库 29,826 决定/26,180 专利/28,623 involves，`based_on` 67,415 条（决定→法条 Article）；文档级 bge-m3 独立 FAISS（限长 4000 字符 + sub_batch=2 规避 oMLX 溢出）；`search_service`/`cnlaw_api`/前端 `LawSearchWorkspace` 双模式（条文/复审无效决定），浏览器端到端验证通过。 |
| 2026-08-26 | 权威度分层（接入「专利模式·CNLaw 底座」）：`_authority_tier` 分层（tier 1 法条/法规/解释/规章 → 2 审查指南 → 3 判例 → 4 书籍），`_rank_hits` 按 `(tier, 现行有效, −score)` 排序，`/search` 命中带 `tier`；修正「分数高的书籍/指南压过法规」。persona 检索次序=法条→指南→判例→书籍，冲突以高权威为准。 |
| 2026-08-26 | 判例定向检索（阶段 B）：`/search/decisions|judgments` 加过滤 `ground`(法条子串,中/阿数字归一)/`ipc`(仅决定)/`result`/`case_type`，命中带 `legal_basis`；`vectorize_judgments` 补 `--backfill-fields` 回填。过滤=FAISS 窗口 k×10 + 纯函数 `_field_filter`。 |
| 2026-08-26 | 图谱精确导航（阶段 C）：新增 `graph_api.py` 挂 8001——`/graph/ground`(based_on 法条→判例,可加 ipc/law)、`/graph/patent`(involves 专利号→判例+IPC)；`cn_num.py` 中/阿数字归一。**当日为 ground 加 `offset` 分页**：`DISTINCT + ORDER BY case_number,id + SKIP/LIMIT`，响应含 `total_decisions`/`total_judgments`/`has_more`，突破每 kind LIMIT 上限（实测 A22.3 下 16,384 决定/1,525 判决，翻页稳定）。 |
| 2026-08-26 | 案件级决策链（阶段 D）：新增 `case_api.py` 挂 8001——`POST /case/{id}/decision`(自动 step+:next 链,首条建 Case)、`GET /case/{id}`、`/chain`；`vectorize_cases.py` 供 `/case/similar` 相似复用；`cnlaw_mcp.py`+launcher 暴露 6 个原生 `mcp__cnlaw__*` 工具（pypi mcp 2.x，`trust_env=False`）。 |
| 2026-08-26 | 现有技术检索为**独立可复用例程**（`patent-prior-art-search` 技能），与 cnlaw「怎么认定」互补：cnlaw 无专利全文，只做法律/指南/判例/分类底座。 |


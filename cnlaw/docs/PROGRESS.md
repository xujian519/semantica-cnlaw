# 开发进度记录

> 更新日期：2026-08-25。
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
- **未覆盖**：各工作区**内部面板**细项文案仍为英文（42 个组件的深层文案，后续增量）。

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

- 纳入部门合计：保留 **1921 份** + 待复核 **217 份**（13 个索引 + 203 个疑似地方性法规 + 1 个攻略），共 2138 个 `.md` 文件，与方案「约 2200 份」基本吻合。
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
- [ ] 待观：57797 条边在 canvas 上的最终渲染性能。

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
| 2026-08-25 | 溯源（provenance）：把 `LegalDocument.path`（源文件完整路径）写入 Neo4j 并随 sidecar `meta` 缓存，检索命中返回 `source_path`，Explorer 溯源行展示「源路径 · 日期 · 状态」，实现逐条可审计；`--backfill-path` 增量补写存量，不重跑向量化/清库。 |
| 2026-08-25 | 法条引用关系：从条文正文提取「本法第X条」（同文档）与「《某法》第X条」（跨文档）引用，经中文数字转阿拉伯 + 简称→全称匹配（唯一子串）+ 现行版选择解析，建 Article→Article `cites` 边（2953 条）；`cnlaw/ingest/citations.py` 为纯函数可测，Explorer 加载 `cites` 类型边（图边 57,797→60,750）。 |
| 2026-08-25 | 失效法律追踪：把「已被修订」7488 条也 `--status 已被修订` 增量向量化进检索池（FAISS 55783 条，sidecar `status` 如实标记）；查询命中「已被修订」时 `score×0.5` 降权，并按「现行有效优先（分组）+ 分数降序」排序（`_rank_hits`），status 明确返回供前端标记——现行有效永远排在被修订前。 |
| 2026-08-25 | 专利知识库（第四层·第一步）：引入 `domain` 属性区分知识域，专利文件标 `domain='专利'`（含回填已有专利法律）。全国性专利法律/法规/司法解释已随中央法规库入图（按 `full_name@source_date` 归并不重复建点）；本步真正新增的是 7 部专利部门规章（代理管理/强制许可/质押登记/标识标注/行政执法/规范申请行为/生物材料保藏）+ 1 部 2026 惩罚性赔偿司法解释（法释〔2026〕7号）；排除地方性法规（鲁/鲁/淄/青）与技术标准《专利申请号标准》。 |
| 2026-08-25 | 解析器增强（支撑专利语料）：`parse_laws.py` 兼容 `_YYYYMMDD` 文件名日期、扁平文档（INFO END 后无章节标题）正文切分、`**第X条**` 粗体条号、块引用/分隔线清理；`load_patent.py` 增量入库（MERGE 不清库）+ `backfill_patent_domain` 关键词「专利」回填；`law.ttl` 新增 `law:domain`；侧车/检索/Explorer 元数据透传 `domain`，前端检索卡右上角展示 domain 标签。 |


# 接线设计：专利模式 → semantica-cnlaw 法条·判例核验通道（REST）

> 状态：**已实现**（2026-08-26）。用户级预设 `patent-cnlaw` 已建成；shipped `patent` 本体保持未动。最终挂载校验以 GUI 真实会话为准。
> 目标：让 DeepSeek Harness 的「专利模式」在"法条核验 / 审查指南引用 / 判例检索 / 证据溯源"上，优先走本地 semantica-cnlaw 权威法律底座，作为现有 `patent_case_search` 的**权威源**。

---

## 0. 目标与非目标

**目标**
- 专利模式把"法条 / 审查指南 / 复审无效决定 / 专利判决"作为**权威法律环境**，经本地 REST 检索并保留 `source_path` 溯源。
- 每条法条/判例断言可给出 `full_name + 条号/案号 + source_path` 可溯源三元组。

**非目标**
- 不涉及现有技术检索（prior-art 仍走 `google-patents-search` / CNIPA / 现有 `patent_search`）。semantica-cnlaw 不含专利全文，只做法律/判例/指南/分类底座。
- 不替换 `patent-workflow` / `patent-rule`（现有流程与门禁不动）。
- 本设计只到"可调用 + 可溯源"；MCP 化、自定义工具为后续可选升级。

---

## 1. 被调方契约（semantica-cnlaw 端）

### 1.1 最小面（检索法条 / 决定 / 判决）
| 端点 | 方法/参数 | 返回关键字段 |
|---|---|---|
| `GET :8100/search` | `q`（语义查询）、`k`（默认 8） | `full_name, number, text, status, domain, category, source_path, score` |
| `GET :8100/search/decisions` | 同上 | `case_number, decision_id, case_type, decision_result, application_number, invention_name, ipc, text, source_path, source_file` |
| `GET :8100/search/judgments` | 同上 | `judgment_id, case_number, case_type, cause, court, decision_result, application_number, text, source_path` |

### 1.2 扩展面（IPC / 图谱浏览）
`GET :8001/api/cnlaw/ipc/sections`、`/tree?parent=`、`/{code}/decisions`。需 explorer + Neo4j。

### 1.3 启动前置（按需启动）
- **必须**：oMLX（bge-m3 嵌入，`:8000`）+ `search_service`（`:8100`，`cnlaw.ingest.search_service:app`）。
- **可选**：explorer（`:8001`）+ Neo4j（`:7687`）——仅 IPC 树 / 图谱 / 前端浏览需。纯法条/判例检索可只起 8100（sidecar 已缓存全文，查询链路不依赖 Neo4j）。
- FAISS 索引与侧车在 `data/vector_store/`、`data/vector_meta/`，零网络、零 API 成本。

### 1.4 已实测请求-响应（验证契约，2026-08-26）
```bash
curl -s -m 40 -G "http://127.0.0.1:8100/search" \
  --data-urlencode "q=专利法 创造性" --data-urlencode "k=3"
# → 命中《专利审查指南 第二部分 实质审查·第四章 创造性》 dom=专利 cat=审查指南
#   source_path=/Users/xujian/projects/宝宸知识库_Raw/审查指南_guide_md/第二部分_第四章_创造性.md
curl -s -m 40 -G "http://127.0.0.1:8100/search/decisions" \
  --data-urlencode "q=区别技术特征 具备创造性" --data-urlencode "k=2"
# → 命中 WX4927：case_type=无效 decision_result=维持专利权有效 法律依据=A22.3 ipc=B05C11/04…
curl -s -m 40 -G "http://127.0.0.1:8001/api/cnlaw/search/judgments" \
  --data-urlencode "q=等同侵权 全面覆盖原则" --data-urlencode "k=2"
# → 命中最高法（2015）民申字第740号：court=最高人民法院 cause=…判决结果=… source_path=…
```

---

## 2. 调用方接线（专利模式端）

### 2.1 最小调用机制：`bash curl`（0 新增工具，0 代码改动）
`tool-bash` 已在专利 preset。统一模板（`--data-urlencode` 免手编中文）：
```bash
curl -s -m 40 -G "http://127.0.0.1:8100/search" \
  --data-urlencode "q=<查询>" --data-urlencode "k=5" | jq
curl -s -m 40 -G "http://127.0.0.1:8100/search/decisions" \
  --data-urlencode "q=<查询>" --data-urlencode "k=5" | jq
curl -s -m 40 -G "http://127.0.0.1:8100/search/judgments" \
  --data-urlencode "q=<查询>" --data-urlencode "k=5" | jq
```
字段提取（`jq` 已装），用于证据附录：
```bash
... | jq '[.results[] | {full_name, number, status, domain, category, source_path}]'
... | jq '[.results[] | {case_number, decision_result, application_number, invention_name, ipc, source_path}]'
```

**证据引用格式（纪律 5）**：`<full_name> 第<number>条 · 来源: <source_path> · domain=<domain> status=<status>`。

### 2.2 可选增强（后续，非本设计范围）
- **web_fetch**：需给 preset 加 fetch provider（如 `@deepseek-ai/dsh-web-fetch-http`）。当前 `fetch:false`，web_fetch 不可用。
- **MCP 化**：`@deepseek-ai/dsh-mcp-client` 接 `semantica-mcp`，原生成 `mcp__semantica__find_precedents` 等——但通用 MCP 不含 cnlaw 检索端点，需另包装，价值再评估。

### 2.3 失败降级
- 服务未启动 → 先探测 `:8100/health`（`{"ready":true,"decisions_ready":true,"judgments_ready":true}`）；不 ready 则**不引用 cnlaw 结论**，回退现有 `patent_case_search`，绝不无来源下结论（纪律 7）。
- 命中为空 → 明确"检索未覆盖，不下结论"（纪律 1/3 复用现成行为）。

---

## 3. Persona 调整点（实施时的目标文本）

> 关键事实：GUI 里的「专利模式」本体是**部署自带的 shipped `patent` 预设**
> （`/Applications/DeepSeek Harness.app/Contents/Resources/backend/config/agent-presets/patent`，
> `preset.yml` 的 `name: 专利模式`，trust=system）。按规则**不可原地编辑 shipped 预设**，
> 因此实现＝**拷贝到用户级预设并改副本**（见 §4），shipped 本体保持不动。
> 以下段落均针对**副本** `agent.cordis.yml`。

- 位置：`~/.dsh/.agent-presets/<副本id>/agent.cordis.yml`（副本由 shipped `patent` 拷贝而来）。

### 3.1 「工具与技能」检索行（现第 56 行）
在现有 `patent_search / patent_metadata / patent_legal_status … patent_case_search / patent_wiki_search / patent_kg_query … web_search …` 之后插入：
```
- 法条/审查指南/判例核验（权威法律底座，本地）：优先走 cnlaw REST——
  curl -sG "http://127.0.0.1:8100/search" --data-urlencode "q=…" --data-urlencode "k=5"
  返回 {full_name, number, text, status, domain, category, source_path}；判例同类
  /search/decisions（复审无效决定）、/search/judgments（专利判决）；IPC 浏览用 :8001/api/cnlaw/ipc/*。
  每处法条/判例断言必须带 full_name（+条号/案号）与 source_path；命中为空的检索不得下任何结论。
```

### 3.2 纪律 3（法条引用必须核验，现第 46 行）
补充"优先用 cnlaw REST 检索《审查指南》/法条/判例原文并取 source_path 溯源，再对照 99-知识库/ 项目基线"。

### 3.3 输出纪律 / 证据附录（纪律 5 附近，现第 63-66 行）
约定：凡引用法条/指南/判例，证据附录须含 `full_name`+`条号/案号`+`source_path`，来源标注 `cnlaw(:8100)`。

---

## 4. 实现方式（因 shipped 不可原地改）

| 步骤 | 动作 | 说明 |
|---|---|---|
| 1 | 拷贝 shipped `patent` → `~/.dsh/.agent-presets/<副本id>/` | 连同 `skills/`、`preset.yml`、README 全量拷贝 |
| 2 | 改副本 `preset.yml` | 设独立 `name`（如 `专利模式·CNLaw`）+ `description`，避免与 shipped 同名混淆 |
| 3 | 改副本 `agent.cordis.yml` | 仅改 persona 文本（§3 三处），**不动**行/realm/服务结构 |
| 4 | 验证 | 副本 YAML 可解析（entryListSchema 方言）+ 与 shipped 逐行 diff 仅差异在 persona 文本 + realm 规则未变 |
| 5 | 挂载 | 用户在 GUI 选副本预设；`standingKeyFor` 或真实会话作最终校验 |

**用户根被扫描**：`dsh-agent-presets` 的 `index.ts` 会向 `config.roots` 追加
`{ path: dshHomePath('.agent-presets'), trust: 'user' }`，故副本必然被发现并出现在预设选择器。

---

## 5. 验收标准

- [ ] `curl -sG :8100/search?q=审查指南 创造性` 返回 `《专利审查指南…第四章 创造性》` + `source_path`（已实测）
- [ ] `curl -sG :8100/search/decisions?q=区别技术特征 具备创造性` 返回决定 + `decision_result / case_number / 法律依据 / source_path`（已实测）
- [ ] 服务未启动时，探测 `/health` 不 ready → 明确"cnlaw 不可用，不引用"，绝不凭空下结论
- [ ] 一条法条/判例断言能给出 `full_name + 条号/案号 + source_path` 可溯源三元组
- [ ] 专利模式 GUI 会话选中副本预设后，persona 出现 cnlaw REST 检索优先规则
- [ ] 全本地、零网络、可重复、可审计

---

## 6. 风险与回滚

- **沙箱网络**：副本内 `bash` 调 `localhost:8100/8001` 需 loopback 放行；本会话已验证可行，如专利模式沙箱收紧需在配置层放行。
- **语义检索非精确字段**：法律引用仍需 AI 判别条文（现有纪律已覆盖）；`k` 调小 + `jq` 只取命中 `full_name/number` 降低误引。
- **IPC 标题 OCR 污染**：已知局限，`code` 权威、标题仅供参考。
- **回滚**：副本是用户级、可删除；shipped `patent` 本体从未改动，删除副本即完全回到原状。

---

## 7. 阶段 B（判例语料接入）—— 已实现（2026-08-26）

> 现状核对：判例语料已**全量入检索池**（决定 29,825 条 / 判决 5,969 条，FAISS + 侧车）；`legal_basis` 决定侧车 **98%**、判决侧车回填后 **87%**。目标是把"能搜到"升级为"**按理由/技术领域/结论定向检索**"。

### 7.1 新增能力（cnlaw 侧，纯 REST，查询路径不依赖 Neo4j）
- `GET :8100/search/decisions`、`/search/judgments` 与 `:8001/api/cnlaw/search/decisions`、`/search/judgments` 新增可选过滤参数：
  - `ground`=法条片断（子串匹配 `legal_basis`，如 `第22条第3款` / `第26条第4款`；**中/阿数字自动归一**——决定用 `第22条第3款`、判决用 `第二十二条第三款`，两者均可命中）
  - `ipc`=分类前缀（如 `B05C`，仅决定；分隔符支持 `,` `、` `，`(全角) `;` `；`(全角) `/` 空格）
  - `result`=结论（如 `维持专利权有效`）、`case_type`=类型（`无效`/`复审`/`民事`/`行政`）
- 命中返回增补 `legal_basis`（以及既有的 `decision_points`/`ipc`）。
- 过滤逻辑在 `search_worker._field_filter`（纯函数，含 `_cn_numerals_to_arabic`/`_cn_num_to_int` 归一）；带过滤时 FAISS 窗口放宽到 `k*10` 防召回不足；**多个过滤条件是合取**，窄组合可能返回少量/空（如实返回、不误报），建议先宽泛检索再加过滤。

### 7.2 已提交改动（cnlaw 侧）
- `cnlaw/ingest/search_worker.py`：新增 `_field_filter`；`query_decisions`/`query_judgments` 加过滤参数、命中带 `legal_basis`、放宽窗口；`_rank_hits` 改为按 (权威层, 现行有效, 分数) 排序、`/search` 命中带 `tier`（见 §7.8）。
- `cnlaw/ingest/search_service.py`、`cnlaw/ingest/cnlaw_api.py`：端点加 Query 参数；`DecisionHit`/`JudgmentHit` 加 `legal_basis`。
- `cnlaw/ingest/semantic_search.py`：客户端透传过滤参数。
- `cnlaw/ingest/vectorize_judgments.py`：`build_metadata` 存 `legal_basis`/`decision_points`；新增 `backfill_fields()` + `--backfill-fields`（离线、不重嵌入）。
- 测试：`cnlaw/tests/test_precedent_filter.py`（9 项）；全套 `cnlaw/tests` 152 项通过。

### 7.3 已实测（端到端，2026-08-26）
```bash
curl -sG "http://127.0.0.1:8100/search/decisions" \
  --data-urlencode "q=区别技术特征 显而易见" \
  --data-urlencode "ground=第22条第3款" \
  --data-urlencode "result=维持专利权有效" --data-urlencode "k=5"
# → 命中 5 条，全部《法律依据=…第22条第3款》+ 结论=维持专利权有效 + source_path
curl -sG "http://127.0.0.1:8100/search/decisions" \
  --data-urlencode "q=权利要求 不清楚 得不到说明书支持" \
  --data-urlencode "ground=第26条第4款" --data-urlencode "k=5"
# → 命中 5 条，全部引《专利法第26条第4款》（A26.4 清楚/支持）
```

### 7.4 接线到专利模式（副本 `patent-cnlaw`）
- persona 新增"判例按理由定向检索"行：使用上述带过滤端点；判例引用格式 `<决定号/案号> + <结论> + <法律依据> + <IPC> + <决定要点(若有)> + <source_path>`，来源标注 `cnlaw(:8100)`。

### 7.5 启用
**须重启检索服务以加载新代码**（旧 8100 进程不带过滤参数）：
```bash
cd /Users/xujian/projects/semantica-cnlaw
source bin/activate-env.sh
# 重启 search_service（8100）
set -a && source .env && set +a && ./.venv/bin/uvicorn cnlaw.ingest.search_service:app --port 8100
# 如需 8001 链路（cnlaw_api/前端/IPC），重启 explorer（8001）+ 确认 Neo4j（7687）
```

### 7.6 阶段 B 边界（诚实）
- 判决侧车**无 IPC**：`ipc` 过滤仅对决定生效；判决按技术领域可用案由/发明名称近似，或走 Neo4j `classified_in`（需按需启动）。
- `decision_points` 仅 ~51%（决定）/ 判决回填后部分：命中无决定要点时只给"结论+法条+溯源"，并标注"决定要点未提取"。
- 语义检索仍非精确字段；法条引用仍需 AI 判别（现有纪律已覆盖）。

### 7.7 验收样例（OA 答复 · 按 A22.3 检索判例，2026-08-26 实测）

**情景**：审查员以 A22.3 创造性（区别特征有技术启示、显而易见）驳回；检索"同样被指显而易见、但最终维持有效（具备创造性）"的决定作反驳依据。

**调用**（persona 约定，`curl` 而非 python urllib/httpx）：
```bash
curl -sG "http://127.0.0.1:8100/search/decisions" \
  --data-urlencode "q=区别技术特征 技术启示 非显而易见" \
  --data-urlencode "ground=第22条第3款" \
  --data-urlencode "result=维持专利权有效" --data-urlencode "k=5"
```

**返回 5 条（均 维持专利权有效，`legal_basis` 含 第22条第3款）**：

| 案号 | 结论 | 法律依据 | 决定要点（摘） |
|---|---|---|---|
| 4W116431 | 维持专利权有效 | 细则43.1 / 26.4 / 22.2 / 22.3 | （主要谈权利要求的**支持**） |
| 4W115140 | 维持专利权有效 | 22.3 / 26.4 / 细则43.1 | **与最接近现有技术存在区别特征，未被其他现有技术公开、无启示** |
| 5W133900 | 维持专利权有效 | 22.3 / 26.3/4 | **区别特征未被公开；现有技术整体无将该特征应用的启示** |
| WX13035 | 维持专利权有效 | 22.4 / 22.3 | （主要谈**实用性**） |
| WX13514 | 维持专利权有效 | 22.3 | （决定要点未提取） |

每条带 `来源：cnlaw(:8100) /Users/xujian/projects/宝宸知识库_Raw/无效复审决定/<文件>.md`。

**结论 / 亮点**：
- 命中 `4W115140`、`5W133900` 是**正中靶心的 A22.3 反驳依据**——决定要点直指"区别技术特征未被公开 / 无技术启示"，正是反击"显而易见"的支撑。
- 部分（`4W116431`、`WX13035`）法条含 22.3 但核心谈他条（26.4 支持 / 22.4 实用性）：`ground` 为**子串**匹配、一决定引多款即命中，靠决定要点判别相关性即可。
- `WX13514` `决定要点未提取` 如实标注（决定要点覆盖 ~51%），不编造。
- IPC 有随分类可选的、也有缺的（`5W133900` 缺）——符合"仅决定有 IPC、部分缺失"边界。
- **整条链路打通**：persona → curl → 8100 字段过滤 → 结构化判例引用 → `source_path` 溯源；persona 用 `curl`（而非 python urllib/httpx）规避了后者对 `localhost` 的代理路由异常（502）。

### 7.8 检索权威度排序（2026-08-26 追加，修正"检索次序"问题）

**问题**：`/search` 端点把 法律法规 + 审查指南 + 书籍 混在一个索引，原排序只按"现行有效 + 分数"，导致分数高的书籍/指南可能压过法规——权威次序不对。

**权威度分层**（`search_worker._authority_tier`，`tier` 越小越权威）：

| tier | 来源 | 说明 |
|---|---|---|
| 1 | 法条/法规/司法解释/部门规章 | 最高权威（行政法规/司法解释/部门规章/各法律域 category） |
| 2 | 审查指南（`category=审查指南`） | 官方审查标准 |
| 3 | 判例：复审无效决定（`/search/decisions`）+ 专利判决（`/search/judgments`） | 独立端点，天然 tier 3 |
| 4 | 书籍（`category=书籍`，如《以案说法》） | 最低，仅说明，不作法规依据 |

**改动**：`_rank_hits` 改为按 `(tier, status==现行有效, -score)` 排序；`/search` 命中带 `tier` 字段（`SemHit`/`LawHit` 透传）。效果：即使某条法规 embedding 分数低于指南/书籍，也排在前面（实测：`q=创造性 三步法 技术启示`，法规 tier=1 score0.52 排在指南 tier=2 score0.54 之前）。

**persona 次序/优先级**（`patent-cnlaw` 已写入 纪律 3 + 核验行）：
> 检索/引用次序：**先法条法规(tier=1) → 再审查指南(tier=2) → 再判例(复审无效决定 /search/decisions、判决 /search/judgments，tier=3) → 最后书籍(tier=4)**。引用按权威度排序；冲突以高权威为准，书籍不作法规依据、仅作背景说明。

**边界**：判例在独立索引（决定/判决），天然是 tier 3、在 /search 中不混入；因此 /search 内部实际只出现 tier 1/2/4，判例由 agent 依序另查。测试：`test_authority_tier`/`test_rank_hits_by_authority_tier`/`test_rank_hits_current_version_first_within_same_tier`（`cnlaw/tests/test_precedent_filter.py`，全套 164 项通过）。

---

## 8. 阶段 C（图谱资源利用）—— 已实现（2026-08-26）

**目标**：把已建好的引用关系图（`based_on` / `involves` / `classified_in`）与 IPC 分类树接进专利模式，从"语义近似搜"升级为"**按关系精确导航**"（更全更准的精确集合）。

### 8.1 新增端点（Neo4j 支撑，:8001 `/api/cnlaw/graph/*`）
| 能力 | 端点 / 参数 | 图关系 | 说明 |
|---|---|---|---|
| **C1 按法条找判例** | `GET /graph/ground?article=&law=&k=` | `-[:based_on]->Article` | 精确返回引用该条的决定+判决；`article` 中文/阿拉伯数字皆可（`cn_num` 归一），`law` 消歧 |
| **C3 技术领域×法条** | 同端点 + `ipc=` | `classified_in` | 取同 IPC 子树（仅决定；判决无 IPC） |
| **C2 按专利号追踪** | `GET /graph/patent?pn=` | `-[:involves]->Patent` | 返回该专利相关决定+判决+IPC |

### 8.2 新增/改动文件
- `cnlaw/ingest/graph_api.py`（新）：两个图谱端点；hits 按 `(kind, id)` 去重（一决定多 IPC 只计一次）。
- `cnlaw/ingest/cn_num.py`（新）：中文↔阿拉伯数字归一（`cn_num_to_int`/`cn_numerals_to_arabic`/`arabic_to_cn`/`extract_article_number`）。
- `cnlaw/ingest/search_worker.py`：数字助手改为从 `cn_num` 导入（保留 `_cn_*` 别名）。
- `cnlaw/ingest/explorer_app.py`：挂载 `graph_router`。
- `cnlaw/tests/test_cn_num.py`（新）：5 项。

### 8.3 实测（2026-08-26）
- `ground?article=专利法第22条第3款&law=专利法&k=8` → 16 条（决定+判决），全部 `中华人民共和国专利法 第二十二条`。
- `ground?article=第22条第3款&ipc=B05C&k=5` → 4 条（去重后）：5W101858 / WX4927 / 5W100164 / 4W106801，均 B05C 子树引 A22.3。
- `patent?pn=95116452.X` → 专利"一种涂布柔性刮刀"，IPC `[B05C1/12, B05C11/04]`，命中 WX4927（维持专利权有效）。

### 8.4 persona 接线 / 依赖
- `patent-cnlaw` persona 新增"图谱定向检索"行（三端点 + 用法 + 引用格式 `cnlaw(:8001/graph)`）。
- **依赖 Neo4j(7687)**：C1–C3 是结构化图谱查询，须 Neo4j 在跑（可按需启动）；语义检索（8100 侧车）仍不依赖 Neo4j。

---

## 9. 阶段 D（案件级决策链审计）—— 已实现（2026-08-26）

**目标**：把每个多阶段专利分析（检索→D1→区别特征→实际解决技术问题→技术启示→结论→撰写/答复）的每一步记成**可持久化、可查询、可复现的"决策链"**，作为案件级审计记录与复用基础。

**为何不用 off-the-shelf Decision Intelligence**：generic semantica 的 `record_decision`/`CausalChainAnalyzer` 走 `ContextGraph(advanced_analytics=True)`——**默认内存图**，进程重启即丢，不适合持久化审计；且 `config.yaml` 的 `graph_store=neo4j` 并未被 ContextGraph 自动采用（cnlaw 图谱走 `make_store()` 直连 Neo4j，而非 context_graph 的 store 抽象）。故阶段 D 在 **cnlaw 原生 Neo4j 图**上建 `Case`/`CaseDecision` 模型，持久、REST、与既有模型一致。

### 9.1 端点（:8001 `/api/cnlaw/case/*`，Neo4j）
- `POST /api/cnlaw/case/{case_id}/decision`：追加一个决策步骤；自动分配 `step` 并以 `:next` 链到上一步；首条自动建 `Case`。
- `GET /api/cnlaw/case/{case_id}`：按步序返回案件全部决策。
- `GET /api/cnlaw/case/{case_id}/chain`：返回因果链（每个决策 → 下一步）。

### 9.2 数据模型（Neo4j）
- `Case {case_id, title, status, created_at}`；`Case -[:has_decision]-> CaseDecision`。
- `CaseDecision {decision_id, case_id, step, category, scenario, reasoning, outcome, confidence, decision_maker, entities[], source_paths[], created_at}`；`CaseDecision -[:next]-> CaseDecision`（步序因果链）。

### 9.3 文件
- `cnlaw/ingest/case_api.py`（新）；`cnlaw/ingest/explorer_app.py`（挂载 `case_router`）。
- persona（`patent-cnlaw`）：新增"案件决策链（审计记录）"行。

### 9.4 实测（2026-08-26）
- 记录三步（检索 200 条 → 区别特征/实际解决技术问题 → 具备创造性/维持有效），`step` 自动 1/2/3；`GET /case` 按步序返回 3 条（带 title/status/证据数）；`GET /case/chain` 返回 `……-1 -> ……-2 -> ……-3`（链尾）。
- 修复：case `title` 曾被后续 step 的空 title 覆盖（`coalesce`）→ 改 `coalesce(nullif($title,''), c.title)`；纯净测试数据已清理。

### 9.5 依赖 / 边界
- 依赖 Neo4j(7687) 在跑（可按需）；`decision_maker` 默认 `patent-agent`、`confidence` 0–1、证据用 `source_paths[]`/`entities[]`。
- 这是**审计/复盘**底座；"按相似场景找历史决策"已在 §10（复用检索）实现；`reasoning` 向量化见下。

---

## 10. 阶段 D 扩展（复用检索 + 工具化）—— 已实现（2026-08-26）

### 10.1 闭环复用：按相似场景检索历史案件决策
- `cnlaw/ingest/vectorize_cases.py`：把每条 `CaseDecision` 的 `scenario+reasoning` 用本地 oMLX 嵌入到独立 FAISS 索引（`data/vector_store/case_decisions.faiss` + 侧车）。重建：`./.venv/bin/python -m cnlaw.ingest.vectorize_cases --rebuild`。
- `GET /api/cnlaw/case/similar?scenario=&k=`（case_api）：语义检索历史案件决策，返回 `case_id/decision_id/category/outcome/reasoning/score`。
- **实测**：`scenario=区别技术特征 有技术启示 所以显而易见` → 命中 95116452X 的 4 条决策，最相关优先（区别特征 0.627 > 技术启示 0.614 > 结论 0.607 > 检索 0.538）。**价值随时间累积**（历史分析变成可检索资产）。

### 10.2 工具化：cnlaw 图谱/案件端点 → 原生 MCP 工具
- `cnlaw/ingest/cnlaw_mcp.py`：用 pypi `mcp`（已 `pip install mcp`，2.x ，`MCPServer`）暴露 6 个 MCP 工具：`cnlaw_graph_ground` / `cnlaw_graph_patent` / `cnlaw_case_record` / `cnlaw_case_get` / `cnlaw_case_chain` / `cnlaw_case_similar`，代理到 :8001 REST（`httpx`，`trust_env=False` 规避 localhost 代理）。
- `cnlaw_mcp_launcher.py`：**强制 pypi `mcp` SDK**——项目根自带同名 `mcp/`（Semantica 的 MCP server）会遮蔽 pypi；launcher 把项目目录从 sys.path 前端移除、再追加到末尾，使 `import mcp` 命中 site-packages、`cnlaw.ingest` 仍可导入。
- patent-cnlaw 预设新增 `mcp-cnlaw` 行（`@deepseek-ai/dsh-mcp-client`，stdio 启动 launcher）→ 会话获得 `mcp__cnlaw__*` 原生工具。
- **验证**：MCP stdio 连接 → list_tools 返回全部 6 工具；`cnlaw_graph_ground` 经 MCP 走通 :8001（`article_number=22, hits=6`）。

### 10.3 依赖 / 边界
- 依赖 pypi `mcp` SDK（`pip install "mcp>=0.6"`，当前 2.x；`FastMCP` 已更名 `MCPServer`）+ cnlaw 服务(:8001)+Neo4j 运行。
- 拉起的 launcher 是本地 venv python；`serverName=cnlaw` 生成 `mcp__cnlaw__*` 工具；**最终挂载/工具面需真实 patent 会话确认**（与其余阶段一致）。
- `cnlaw_mcp` 的 httpx 用 `trust_env=False`，避免宿主代理把 `localhost:8001` 路由成 502（本会话已多次遇到）。

---

## 11. 现有技术检索（可复用组件）—— 已实现（2026-08-26）

**定位**：现有技术检索是 patent 模式的**独立可复用例程**，**不是 cnlaw 的能力**（cnlaw 无专利全文，只做法律/指南/判例/分类）。本组件负责"找对比文件 D1/D2/D3"，被 交底书理解 / 新颖性 / 创造性 / 无效 / 答复 / 侵权比对 等场景复用，与 cnlaw 的"怎么认定"并行互补。

**形式**：可复用技能（模型 A，用户选定）。`patent-cnlaw/skills/patent-prior-art-search/SKILL.md` 重写为**可执行例程**：检索要素提取 → 检索式（CN/EN + IPC）→ ask_user 确认 → 分通道执行 → 合并去重 → 遴选 D1/D2/D3 → 落盘 → 证据附录。

**通道策略**（优先 + 回退）：
- **CNIPR**（`cnipr-search-download`，`search.cnipr.com`，ego_browser）：CN 检索 + 全文 PDF（直链必须 `http://` 前缀、`https` 超时）+ 单篇著录项 .xls（L1 免费）；概览页 PDF下载/批量著录/XML 为 VIP。
- **CNIPA**（`cnipa-query` / CNIPA PSS）：官方法律状态 / 著录项权威核验（双源一源）。
- **Google Patents**（`google-patents-search`）：外国 / 全球。
- **web_search**（NPL 文献）、**patent_search**（本地 nuo）：辅助。

**硬规则**：检索未覆盖即声明、不得下新颖性结论；关键事实双源交叉；对比文件公开日早于目标申请日；CNIPR PDF 只从详情页抽 `PDF_PID`、一律 `http://`。

**persona**：「检索」行已更新为"现有技术检索优先走 `patent-prior-art-search` 技能"，并列 CNIPR/CNIPA/Google/Web/本地通道。

**边界**：本技能是**编排层**，实际通道执行走各自技能（Google Patents / CNIPA / CNIPR 需网络 + 登录态）；结构化校验已通过，**真实通道检索需在专利会话内验证**（网络/登录环境），此处无法离线实测。

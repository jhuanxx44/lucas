# Lucas 推倒重来规划：基于 Single 模式重建

日期：2026-07-20
状态：待评审

## 0. 背景与目标

现状：项目内存在两代逻辑并存——

- **新**：`harness/` 通用 AgentRunner（单 agent ReAct 循环）+ `evals/` 评测体系，Phase 0 已完成，质量高、与业务基本解耦。
- **旧**：`agents/` 业务流水线（Manager dispatch + researcher 固定 DAG），仍扛着 server 聊天链路和 wiki 知识入库两条生产路径。

**目标**：删除 `agents/` 全部旧逻辑，产品后端只保留一条路径——`harness/AgentRunner` single 模式。保留：

1. **前端 UI**（`web/` 全部，含三栏布局、ChatPanel、WikiSidebar、SourceUploadDialog）——原则上零改动。
2. **wiki 的设计思想**（见第 3 节），不保留其 932 行的 `KnowledgeService` 实现。
3. `evals/` 评测体系、`utils/` 中解耦的基础设施（llm_client、providers、web_search、stock_data、json_extract、token_tracker）。

**非目标**（明确不做，避免趁机扩大范围）：

- 不实现 Phase 2 的 Planner、Phase 3 的 Validator/Revision 机制（留好挂点即可）。
- 不做多用户（`user_id` 恒 default 维持现状，但删掉 `workspaces/` 迁移残留）。
- 不把子串召回升级为 embedding（记入 backlog）。
- 不改 SSE 事件协议和 Wiki API 字段（前端零改动是硬约束）。

## 1. 总体策略

**先建后拆（build-then-cut）**：先把新链路建好并通过测试，再删旧代码。每个阶段结束都有可验证的验收标准，任何一步失败都可以停下，不留半成品。

执行顺序按依赖解除排列：

```
M1 结构解耦（harness 不再 import evals/agents）
M2 harness 产品化缺口（异步工具、usage、配置）
M3 业务工具注册（web_search / stock_data / wiki 召回）
M4 新聊天链路（Runner → SSE 桥，前端零改动）
M5 wiki 知识模块重建（保留设计思想，新实现）
M6 切换 + 删除 agents/ 与旧测试
M7 收尾（配置精简、文档、实验记录）
```

## 2. 目标架构

```
server/
  app.py / routers/{chat,wiki,sessions}.py     # 基本不动
  services/
    session_store.py                           # 不动
    wiki_parser.py                             # 不动
    agent_stream.py                            # 新：AgentRunner → SSE 桥（替代 stream.py）
    knowledge.py                               # 新：wiki 收录/编译（替代 agents/knowledge_service.py）
harness/
  runner.py                                    # 解除 evals import，支持异步工具
  models.py                                    # 新：RunLimits/AgentResult/StepContext（自 evals 上移）
  trace.py                                     # 新：TraceRecorder 协议/实现（自 evals 上移）
  model_adapter.py                             # complete 返回 (text, usage)
  tools/{registry,filesystem,search}.py        # 不动
  tools/business.py                            # 新：web_search/stock_quote/wiki_recall
  config.py                                    # 新：读 lucas.yaml 的 agent 配置
agents/                                        # 删除
utils/                                         # 保留（verify.py 删除，source_collector 改工作区相对路径）
evals/                                         # 原样保留，仅 adapter 装配改配置来源
lucas.yaml                                     # 替代 agents.yaml（删 manager/researchers 段）
```

关键边界（来自 AGENTS.md 与路线图）：

- `harness/` 不 import 任何业务模块与 `evals/`；产品 single path 与 eval adapter 共用同一个 `AgentRunner`，不维护影子实现（roadmap Phase 9 验收）。
- 执行语义（超时、熔断、权限、终止）由代码保证；行为策略（工具使用偏好、输出风格）进 `prompts/` 模板并标注 `llm-weight`。
- `raw/` 不可变；派生写入只发生在各自目录。

## 3. 保留的 wiki 设计思想（重建依据）

来自对 `agents/knowledge_service.py`、`prompts/wiki-*.md`、`docs/lucas-design-review.md` 的提炼，新实现 `server/services/knowledge.py` 必须守住这些设计决策：

1. **四层存储边界**：`raw/`（只读）→ `ingested/`（收录）→ `reports/`（归档）→ `wiki/`（编译视图），单向流动，下游可从上游重建。
2. **来源与页面分离**：原始材料带 frontmatter（source/title/date/type），wiki 页面 frontmatter 的 `sources:` 声明由哪些来源编译而来；用声明式溯源代替编译状态数据库。
3. **Plan → Compile 两段式**：LLM 先输出结构化 JSON 计划（写哪页、create/update、理由），再按计划逐页编译；决策可校验，写作自由。
4. **LLM 写入前确定性校验 + 备份**：frontmatter 必填字段校验、更新丢失检测、写前 `.bak`。
5. **增量更新语义**：保留旧内容、新增标注日期、新旧矛盾并存标注。
6. **收录两段确认**：classify（LLM 提议 + confidence + alternatives）→ 用户确认 → ingest（落盘 + 定向编译该来源）。
7. **索引优先召回**：`wiki/index.md` 为人类与 LLM 共用入口；先索引匹配再全文 fallback，页面截断注入。

可丢弃的实现细节（不随迁）：申万行业/{代码}-{简称} 等 A股硬编码（参数化）、字符串拼装的 index.md 维护、手写 frontmatter 扫描（统一走 yaml）、LLM 整页覆盖写（本版保留但记 backlog：改 patch/event sourcing）、单份 `.bak`。

## 4. 里程碑详案

### M1 结构解耦（纯移动，无行为变化）

- 把 `RunLimits`、`AgentResult` 等 Runner 需要的类型从 `evals/harness/models.py` 上移/复制到 `harness/models.py`；`TraceRecorder` 上移到 `harness/trace.py`，evals 侧改为 re-export 或 import harness。
- `harness/runner.py` 删除对 `evals.harness.*` 的 import；`TraceRecorder` 参数改为可选（产品路径可关 trace）。
- **验收**：`pytest tests/test_harness_runner.py` 全绿；`python -m evals.harness run-suite` 结果与基线一致。

### M2 harness 产品化缺口

- 异步工具：`ToolHandler` 支持 `async def`（`registry.execute` 改 async，Runner await）。同步 handler 继续兼容。
- `ModelAdapter.complete()` 返回 `(text, usage)`；Runner 累计 TokenUsage 写进 AgentResult；`max_cost_usd` 开始被消费（超预算终止）。
- 新 `harness/config.py`：`load_agent_config()` 从 `lucas.yaml` 读 `single_agent` 段（provider/model/max_steps/allowed_tools 默认值）。eval adapter 与 server 都用它，解除对 `agents.config` 的依赖。
- **验收**：新增测试——异步工具在一个 run 内被 await 执行；usage 进入结果；adapter 不再 import `agents`。

### M3 业务工具注册（`harness/tools/business.py`）

首批三个工具（按 roadmap"不一次迁完全部能力"）：

- `web_search`：薄包 `utils/web_search.search`。
- `stock_quote` / `stock_kline`：按 provider 方法粒度拆 `utils/stock_data.py`，不做"从问题提取股票代码"的 LLM 前置（参数由模型在 tool args 里直接给代码）。
- `wiki_recall`：索引优先召回，复用 `server/services/wiki_parser.py` 的解析（上移为 `server/services/` 与 harness 都可 import 的位置，如 `wiki/core.py`），先 index.md 匹配再全文 fallback，top N 截断注入。

每个工具：ToolSpec + `llm-weight` 标注的 prompt 片段 + 权限白名单接入。
- **验收**：为每个工具写 eval task（或扩展 capability suite），固定 task + 确定性 grader；与 baseline 对比记录进 experiment-log。

### M4 新聊天链路（前端零改动）

- 新 `server/services/agent_stream.py`：构造 AgentRunner（业务工具白名单 + 会话 history 注入 instruction 上下文），把 run 过程映射为现有 SSE 事件：
  - run 开始 → `researcher_start {id: "single"}`
  - 每个工具 step 完成 → `status {message}`（事件级流式，非逐 token；JSON-per-step 协议与逐 token 流式天然冲突，本版接受事件级）
  - answer → 作为 `synthesis_chunk` 一次性或分段推送 → `researcher_done` → `done {total_tokens}`
  - 异常 → `error {message}`
- `routers/chat.py` 切到新 service；`dispatch`/`actions` 事件不再发（前端缺省正常，文案退化为"分析过程"，可接受）。
- **验收**：`tests/test_chat_sse.py` 改造后通过（事件序列断言更新）；手工跑前端完成一次完整问答；session 落盘格式不变。

### M5 wiki 知识模块重建（`server/services/knowledge.py`）

按第 3 节设计思想重写，接口保持 `classify-source`/`ingest-source` 的返回字段与 SSE 事件名（`status/saved/compiled/done/error`）：

- classify：LLM 轻量分类（保留 confidence + alternatives 契约）。
- ingest：落盘 `ingested/`（frontmatter 补齐）→ 定向 plan → compile → 校验 → 备份 → 写 wiki → 重建 index.md（结构化重建，不用 str.replace）。
- 领域本体（行业列表、命名规则）进 `lucas.yaml`，不进代码。
- 前端 Wiki API 的 10 个文件操作端点不动。
- **验收**：迁移 `test_storage_boundaries.py` / `test_report_sidecars.py` 到新模块（raw 快照逐字节不变等约束必须继续通过）；SourceUploadDialog 全流程手工验证。

### M6 删除旧代码

确认 M4/M5 上线后：

- 删 `agents/` 全目录、`utils/verify.py`、`agents.yaml`（内容已并入 `lucas.yaml`）、`migrate_to_workspace.py` 与 `workspaces/` 残留、`prompts/` 下仅旧体系使用的模板（dispatch/synthesis/claim-extract/wiki-plan 等——其中 plan/compile 模板的思想已并入新模板）。
- 删 6 个直接测 agents 的测试文件（M5 已迁移其中仍有价值的约束）。
- **验收**：`grep -r "from agents\|import agents" --include="*.py"` 零命中；全量测试绿；`python -m evals.harness run-suite` 绿；server 启动 + 前端冒烟通过。

### M7 收尾

- README、AGENTS.md 引用更新；`docs/harness/experiment-log.md` 记录本次重构（作为 Phase 9 提前启动的实验记录）。
- backlog 登记：embedding 召回、wiki patch/event sourcing、Planner 实验（READ-02 探针）、Validator（LIST-01 驱动）、中止机制、超时层级。

## 5. 风险与对策

| 风险 | 对策 |
|---|---|
| 聊天 SSE 事件语义退化（dispatch/actions 没了） | 前端缺省行为已确认正常；文案退化可接受，后续顺手调 |
| 事件级流式体验下降（不再逐 token） | 本版接受；backlog 登记"answer 阶段逐 token 流式"（answer 无工具调用，可安全 stream） |
| evals 与产品共用 Runner 后相互污染 | M1 解耦先行；路线图 11.7 风险条作为评审检查项 |
| wiki 重建丢失隐性约束 | M5 先迁移两个约束测试再写实现；第 3 节清单作为 code review 检查表 |
| 删 agents 后有遗漏引用 | M6 的 grep 零命中 + 全量测试 + eval suite 三重验收 |

## 6. 工作量粗估

M1 半天；M2 一天；M3 一到两天（含 eval task）；M4 一天；M5 两到三天（最重头）；M6 半天；M7 半天。总计约 6–8 个工作日，可按里程碑独立交付。

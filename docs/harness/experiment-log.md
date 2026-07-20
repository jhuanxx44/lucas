# Experiment Log

按路线图"干中学"节奏 Step F 记录：每次实验的假设、实现、指标变化、代表性 replay、被证伪的判断、下一阶段决策。

---

## 2026-07-19/20：Harness Phase 0 落地与首轮机制修复

### 背景

本轮把 Eval Harness 从"只有 2 个 smoke 任务和 Oracle 自验"推进到"真实模型（lucas-single）可运行、trace 可复盘、失败可归因"的状态，并完成了第一次完整的"trace 复盘 → 机制修复 → 对照验证"循环。

### 一、已完成的建设

**共享 Agent 运行时（harness/）**

- `AgentRunner` 最小循环（model → tool → observation → model），产品与 Eval 共用
- 工具集：read_file（offset/max_chars）、list_files、search、apply_patch（唯一替换）、write_file（默认拒绝覆盖）
- `evals/harness/adapters/lucas_single.py` 接入评估，`run-suite` 支持 suite 批量执行与汇总

**Trace 补全（关键设施）**

- 每步记录 `prompt_rendered` / `model_call_started/finished` / `action_parsed`，完整 prompt 与模型原始输出写入 `artifacts/`，observation 全文内联于 `tool_call_finished`
- 埋点 `observation_chars` / `total_observation_chars`，为 Phase 4 Context 实验记账

**题库（capability-v1，5 题）**

| 任务 | 测量能力 | 累计真实表现 | 状态归因 |
|---|---|---|---|
| READ-02 | 长文导航（只许 read_file） | 修复前 8 trial 约 5 过 3 挂；修复后 3/3 | model（导航策略）→ 已转为 Phase 2 探针 |
| READ-03 | 关键词定位（search） | 稳定通过（1 步命中） | — |
| LIST-01 | 工作区盘点 | 6+ trial 错 2 | model（"其中"指代理解偏差，已确诊） |
| EDIT-02 | 歧义编辑（apply_patch） | 稳定通过 | — |
| WRITE-01 | 新建文件（write_file） | 首次即通过 | — |

### 二、代表性实验：READ-02 导航失败与机制修复

**假设**：READ-02（38 万字符招股书定位章节）的失败来自模型导航策略。

**失败复盘（trace 证据）**

1. 第一次失败：12 次跳读中 4 次重读开头区域；形成正确夹逼区间后探测点全部落在区间外。归因：状态追踪缺陷
2. 第二次失败：模型第 5 步就输出了**完全正确的答案**，但用了裸 JSON（无 `{"action":"answer"}` 外壳），被判 invalid；且 invalid 反馈文案"不是合法 JSON"事实上错误，模型连续 3 次原样重发。归因：**机制缺陷**，不是模型问题

**机制修复**

- `_parse_action` 增加 fallback：无 action 外壳的 JSON 对象按 answer 接受
- invalid 反馈文案改为明确说明两种外壳格式

**对照结果**：修复后 READ-02 3/3 通过，且轨迹质量显著改善（零 invalid、零重读开头，出现三种有效策略：直接夹逼 6 步 / 地图式粗扫 8 步 / 线性+跳跃 10 步）。

**结论**：保留修复。失败复盘证明"答案对、格式错"属于 harness 宽容度问题，不应计入模型失败。

### 三、出题修正：READ-02 改题

原题（三个专利数字）存在捷径：数字在招股书前段概要也出现过，模型不走目标章节也能答对。改为"研发人员情况"表格的四年人数（其中 2,891 和 2,606 全文仅出现一次），捷径被堵死。

**出题原则（沉淀）**：

- 预期答案的关键事实应**全文唯一**或仅在目标位置可得，出题时用 grep 验证出现次数
- 要测策略能力，fixture 需包含可利用的元信息（目录/索引），让"会规划的模型"能跑赢"线性执行的模型"

### 四、被证伪或修正的判断

1. ~~"READ-02 改善是因为 read_file max_chars 调大"~~ —— 证伪。Runner 存在 4000 字符二次截断，模型实际看到的页面没变。教训：**trace 不完善时的归因不可信**；机制改动后必须确认真实生效路径再下结论
2. ~~"LIST-01 失败原因待查"~~ —— 通过补全的 trace 确诊：模型把"其中最大的文件"理解为所有文件而非 yaml 文件，信息获取无缺陷，纯理解偏差。归因 model 类，留待 Validator 实验
3. ~~"模型不会利用目录跳读可能是机制问题"~~ —— 部分证实部分搁置：修复协议缺陷后模型展现了三种有效导航策略；但"预算可见/策略提示"两个 prompt 层面的改进**决定不做**，保持 READ-02 作为裸能力探针

### 五、当前 baseline 固定项（供未来对照）

- 模型：providers.yaml 默认（DeepSeek），temperature=0
- prompt：`prompts/harness/tool-loop.md`（无预算提示、无导航策略提示）
- READ-02：max_steps=12，allowed_tools=[read_file]，read_file 默认 max_chars=16000
- 成功率参考（小样本）：READ-02 修复后 3/3；LIST-01 约 4/6；其余 3 题稳定通过

### 六、下一阶段决策

- **READ-02 登记为 Phase 2（Planner）导航能力探针**，不做任何调优。假设：结构化状态/显式规划能提升长文导航的成功率和效率（当前 prompt 消耗 8.5 万-19.3 万字符/run）
- **LIST-01 登记为 Phase 3（Validator）候选驱动案例**："答案是否回应题目约束"的校验有望拦截指代错误
- **READ-03 / EDIT-02 / WRITE-01 稳定通过**，攒满 3+ trials 后可迁入 regression suite
- 已知粗糙项（不阻塞）：trials 样本小；上下文无预算（Phase 4 实验变量）；run-suite 跑全套超 5 分钟需分批（需要时再加 --tasks 过滤）

### 七、产物位置

- runs：`runs/<suite>-<时间戳>-<hash>/runs/<task>-<hash>/`（manifest / trace.jsonl / result.json / artifacts/ / workspace/）
- 代表性 replay：修复前失败 `runs/tmp-read02-20260720-000317-aae0dde6/runs/read-02-fed6c05c7623`；修复后成功 ×3 `runs/tmp-read02-20260720-003325-96570d18/runs/`

---

## 实验 002：Runner 历史结构（observations-only → 全量消息回放）（2026-07-20）

### 假设

让模型在每轮能看到自己之前的原始输出（调了什么工具、参数、答案草稿），改善多步骤任务的状态追踪与自我纠错。单变量：仅历史结构；模型、prompt 其余部分、工具、limits、任务集不变。

### 实现

- `StepContext.observations` → `history`（`{"role": assistant|tool, "content"}`），模型原始输出（含格式错误的）原样入历史
- `_render` 按序渲染为 `【你】/【工具】` 交错段落；invalid 反馈作为 tool 侧消息入历史
- 仍走单 prompt 字符串渲染，不改 ModelAdapter 接口（切原生 messages API 是另一个独立实验）
- 新测试 `test_history_replays_model_raw_output`：第二轮 prompt 同时含第一轮模型原始输出和 observation（旧结构做不到，测试即假设的可证伪形式）

### 结果（capability × 3 trials，对照同条件 baseline）

| 指标 | baseline（改造前） | 改造后 |
|---|---|---|
| 成功率 | 15/15 | 14/15 |
| READ-02 | 4/4/5 步全过 | 4 步过 / 7 步过 / 1 步挂 |
| prompt_chars（READ-02 单 run） | 10.8-13.6 万 | 12.4 万 / 28.0 万（7 步） / 769（挂） |
| 其余 4 题 | 稳定 | 稳定，prompt_chars 微涨（回放原始输出，增量小） |

### 结论

1. **保留改动**。架构上这是路线图已确认的正确结构（Codex/mini-swe-agent 均为全量回放），小样本未显示退化，成本增幅主要来自步数而非回放机制本身（模型输出很小，observation 累积才是大头，两者共有）。
2. **新失败模式登记**：READ-02 T3 模型第 1 步零观察直接幻觉作答（432/516/538/527，正确值 2606/2891/…）。第一步 prompt 与旧结构几乎相同，倾向归因为模型随机性而非历史结构，但它暴露的缺口真实存在——**"无依据直接作答"没有任何拦截**。登记为 Phase 3 Validator 第二个驱动案例（答案是否有 observation 支撑）。
3. baseline 参考更新：历史结构=全量回放，READ-02 成功率约 5/6（小样本）。

### 产物

- baseline suite：`runs/capability-v1-20260720-012217/012325/012406-*`
- 实验组 suite：`runs/capability-v1-20260720-012830/012941/013055-*`
- 幻觉失败 run：`runs/capability-v1-20260720-013055-6c7e16be/runs/read-02-*`

### 追加样本（2026-07-20 第二轮，worktree 同代码 × 3 trials）

| 任务 | T1 | T2 | T3 |
|---|---|---|---|
| READ-02 | ✅ 6 步 / 21.8 万 | ✅ 3 步 / 5.1 万 | ✅ 11 步 / 90.0 万 |
| READ-03 | ✅ 2 步 | ✅ 2 步 | ✅ 2 步 |
| LIST-01 | ✅ 2 步 | ✅ 2 步 | ✅ 2 步 |
| EDIT-02 | ✅ 4 步 | ✅ 3 步 | ✅ 3 步 |
| WRITE-01 | ❌ 2 步 | ❌ 1 步（零观察幻觉） | ✅ 3 步 |

- suite：`runs/capability-v1-20260720-015511/015605/015641-*`（worktree 内）
- READ-02 三过且第 1 步均为正常 read_file 调用；prompt_chars 波动巨大（5 万-90 万），成本不稳定是主要风险
- **"零观察直接作答"失败模式在 WRITE-01 上复现**（此前该题 6/6 稳定）：T2 第 1 步直接 answer 返回正确 path 但根本没创建文件；T1 调了 list_files 但 2 步内未完成写入。两轮累计幻觉失败 3 例（READ-02 ×1、WRITE-01 ×2），出现在不同任务上，且第一步 prompt 与旧结构几乎一致——进一步倾向与历史结构无关，是模型层的"抢答"倾向
- 累计数据强化 Phase 3 Validator 优先级：**"答案必须有 observation 支撑"的校验能拦截全部 3 例幻觉**（零工具调用即作答 / answer 与文件状态不符）
- **WRITE-01 易发幻觉的任务设计原因**：答案键白送——instruction 明确给出了文件名，要求的返回 JSON 又只有 path 一个字段，模型不执行任何写操作也能"算"出标准答案（T2 的 answer_json grader 假阳性通过）。对比 READ-02 答案必须从文件读出，不读就编不对。教训：**出题时避免让"最终答案"可以从 instruction 直接推导**，尤其写操作类任务
- **grader 分层有效性实证**：WRITE-01 幻觉场景下 answer_json（格式对）假阳性，file_content（事情真做了）兜底拦截。说明 outcome grader 必须区分"答案格式正确"与"环境状态真实改变"，现有分层设计恰好覆盖
- Validator 拦截规则候选（机械可判，无需 LLM）：answer 引用的文件必须在 trace 中有对应写操作且存在于工作区；拦截后反馈给模型补救而非直接判死

---

## 实验 003：Single 模式推倒重来重构（Phase 9 提前启动，M1–M7）（2026-07-20）

### 背景

项目内两代逻辑并存：`harness/` 通用 AgentRunner（Phase 0 产物）与 `agents/` 旧业务流水线（Manager dispatch + researcher 固定 DAG）各扛一条生产路径。按规划文档 `docs/plans/2026-07-20-single-mode-rewrite.md`，把 roadmap Phase 9「接回 Lucas」提前启动：产品后端只保留一条路径——`harness/AgentRunner` single 模式，删除 `agents/` 全部旧逻辑。策略为**先建后拆（build-then-cut）**：新链路建好并验收后再删旧代码，共七个里程碑（M7 为收尾）。

### 六个里程碑的关键决策

- **M1 结构解耦**：`RunLimits/AgentResult/StepContext` 与 `TraceRecorder` 从 evals 上移/复制到 `harness/models.py`、`harness/trace.py`，Runner 解除对 `evals.harness.*` 的 import，trace 参数改为可选（产品路径可关 trace）。纯移动，无行为变化。
- **M2 产品化缺口**：`ToolHandler` 支持 `async def`（registry.execute 改 async，同步 handler 兼容）；`ModelAdapter.complete()` 返回 `(text, usage)`，Runner 累计 TokenUsage 写进 AgentResult，`max_cost_usd` 开始被消费（超预算以 `budget_exceeded` 终止；约定 `max_cost_usd <= 0` 视为不限）；新增 `harness/config.py::load_agent_config()` 从 `lucas.yaml` 读配置，eval adapter 与 server 共用。
- **M3 业务工具注册**：工具现按职责拆到 `harness/tools/generic/` 与 `harness/tools/business/`；`web_search` 薄包 utils，`stock_quote`/`stock_kline` 按 provider 方法粒度拆（不做 LLM 前置提取股票代码），`wiki_recall` 索引优先召回（wiki 解析核心在 `utils/wiki_core.py`，先 index.md 匹配再全文 fallback）。
- **M4 新聊天链路**：`server/services/agent_stream.py` 以 Runner `on_event` 钩子把 run 过程映射为既有 SSE 事件——run 开始固定发 `researcher_start {id: "single"}`、每个工具 step 发 `status`、answer 作为 `synthesis_chunk` 推送、`researcher_done`/`done {total_tokens}`、异常发 `error`。取舍：事件级流式而非逐 token（JSON-per-step 协议下模型输出必须完整才能解析，逐 token 与协议天然冲突，本版接受）。`dispatch` 最初停发，review 发现前端 wiki 联动依赖它后已补发（`c95e00c`）；`actions` 不再发送（前端缺省行为正常）。前端零改动。
- **M5 wiki 知识模块重建**：`server/services/knowledge.py` 重写，保留旧实现的 7 条设计思想（四层存储边界、来源与页面分离的声明式溯源、Plan→Compile 两段式、写入前确定性校验+备份、增量更新语义、收录两段确认、索引优先召回）；丢弃 A 股硬编码、字符串拼装 index.md、手写 frontmatter 扫描等实现细节。报告 sidecar 机制不迁移（reports/ 归档层整体未接回，见 backlog）。
- **M6 删除旧代码**：删 `agents/` 全目录、`utils/verify.py`、`agents.yaml`、`migrate_to_workspace.py` 及 6 个直接测 agents 的测试文件，合计 -4135 行；`grep -r "from agents\|import agents"` 零命中。

### 验收证据

- 全量测试 **143 个通过**（`pytest tests/ --ignore=tests/test_llm_connectivity.py`）。
- eval smoke suite（READ-01/EDIT-01）全过。
- 真实 LLM 冒烟：stock_quote 问答（聊天链路经 AgentRunner 调行情工具作答）与 classify-source（wiki 收录两段确认第一段）均通过。
- M6 三重验收：grep 零命中 + 全量测试绿 + server 启动/前端冒烟通过。

### 与 roadmap Phase 9 验收逐条核对

| Phase 9 要求 | 结果 |
|---|---|
| 产品 single path 与 Eval Adapter 调用同一个 AgentRunner，不维护影子实现（接入顺序 1 / 目标） | ✅ server 的 agent_stream 与 evals adapter 都装配同一个 `harness.AgentRunner` + `load_agent_config()` |
| 现有业务测试不回退 | ✅ 143 测试全绿，wiki 约束测试（存储边界等）已迁移到新模块 |
| 真实执行可生成同 schema 的 trace（脱敏后 replay） | ⚠️ 部分：trace schema 统一且 Runner 支持，产品路径默认关 trace；脱敏与保留策略未做（对应接入顺序 6，未启动） |
| 通用 Harness 核心不依赖投研业务模块 | ✅ Runner/ToolRuntime 不 import 具体工具；业务工具在 `harness/tools/business/`，由 server/evals 装配 |
| 业务 adapter 可自行注册工具、context provider 和 validator | ⚠️ 部分：工具注册已通用化；context provider / validator 挂点未建（留 Phase 2/3） |
| 被实验否定的机制不因产品已有类似代码而强行接入 | ✅ Planner/Validator 未提前实现，仅登记 backlog 与探针任务（READ-02 / LIST-01） |

### Backlog（按优先级不分先后登记）

1. answer 阶段逐 token 流式（answer 无工具调用，可安全 stream；目前是事件级）
2. Evaluation Harness 稳定后做 Wiki 访问策略消融：A=限制在 `wiki/` 的只读 `list_files+search+read_file`，B=当前 `wiki_recall`，C=仅在 B 已证明有价值但排序不足时实现 BM25。以答案正确率/无依据作答率为主，比较步骤、Token、延迟和上下文；A 持平或更优且成本可接受时允许直接删除 `wiki_recall`，embedding 仅在 BM25 后按失败归因考虑
3. wiki 写入改 patch/event sourcing（`docs/lucas-design-review.md` 的建议；本版保留整页覆盖写）
4. Planner 实验（READ-02 探针驱动，Phase 2）
5. Validator 实验（LIST-01 指代错误 + READ-02 T3 无依据作答两个驱动案例，Phase 3）
6. 中止机制（`timeout_seconds` 已在 review 修复中由 runner 强制实施，见实验 003 补充）
7. TokenUsage 价格表按 provider 区分（目前单一价格假设）
8. reports/ 层归档恢复（sidecar 未随 M5 迁移，需重新设计）
9. wiki 更新的丢失段落检测从警告升级为拒绝写入（待实践验证误报率）
10. `workspaces/` 残留 5.9MB 用户数据待用户确认处置
11. 业务工具 eval task（web_search/stock_quote/wiki_recall 的固定 task + 确定性 grader，需真实 LLM key 跑 baseline 对照）
12. 行业页等编译校验失败时让模型重试一轮（E2E 实测：LLM 生成缺 frontmatter 的页面被校验跳过后永久缺失）
13. wiki search snippet 剥离 frontmatter、404 文案中文化（E2E 体验项）
14. ingest status 文案与实际落盘路径对齐（`company/X` vs `companies/{行业}/X.md`，仅展示层）

### Review 与端到端验证（2026-07-20 补充）

- 系统 review（全 diff + 前端契约逐字段核对）发现 1🔴5🟠，已全部修复于 `c95e00c`：dispatch 事件补发（wiki 联动回归）、runner 强制 `timeout_seconds`（finish_reason=timeout）、客户端断开 cancel run、写入前代码强制 sources 溯源、聊天白名单显式列出工具名、classify/ingest HTTP 层错误收尾；测试增至 **157 个**。
- E2E 验证（真实 LLM + git worktree 隔离写路径）：聊天 SSE 事件序列、多轮 history、wiki_recall 召回、wiki 只读端点结构、sessions CRUD、classify/ingest 全流程（契约/落盘/sources 强制/索引重建/幂等）全部通过；项目根真实数据零污染。
- E2E 追加修复：异常路径不再外抛 provider 英文报错与掩码 key（统一中文兜底）。

### 产物

- 规划：`docs/plans/2026-07-20-single-mode-rewrite.md`
- 关键提交：M1 `91a0095`、M2 `3f595a4`、M3 `ea0fe80`、M4 `b95bb7c`（聊天链路切换）、M5 `c822f64`、M6 `c3b1389`
- 干中学教程：`docs/learnings/2026-07-20-single-模式重构.md`

## 实验 004：Answer 阶段逐 token 流式（增量 JSON reply 提取）（2026-07-20）

- 来源：实验 003 backlog #1；规划 `docs/plans/2026-07-20-answer-streaming.md`。
- **机制决策**：选「流式输出原 JSON + 增量解析提取 reply 字符串」（`harness/streaming.py` 的 `AnswerStreamParser`），放弃「`FINAL:` 标记协议」——后者要改 prompt 模板与输出契约，且与 DeepSeek `json_object` 模式冲突（不接受纯文本），模板是 eval 共用件，改动会造成评测行为漂移。增量解析零契约改动、evals 默认关闭零影响，新组件可独立单测。
- **设计要点**：parser 三态 DECIDE/STREAM/BUFFER，只有确认 `"reply": "`（字符串值）才开始推送；工具调用、非字符串 reply、非法 JSON 绝不泄漏半个字到前端。完整 raw 仍走 `_parse_action` / trace / 全量回放，与非流式一字不差。流式异常记 `answer_stream_fallback` trace 后回退 `complete()`，run 不中断。`agent_stream` 把 `answer_chunk` 桥接为 `synthesis_chunk`，结束按 `streamed_chars` 补尾防缺字。
- **验证**：测试 157 → 178 全绿（parser 9 例 + Runner 5 例 + agent_stream 3 例 + 既有回归）；eval smoke（READ-01 / EDIT-01）全过，证明评测路径零变化；真实冒烟（临时 server + curl -N /api/chat，DeepSeek 真实流）`synthesis_chunk` 逐字到达 62 次，拼接完整，server 已关闭。
- **遗留**：流式无 usage（OpenAI 兼容流未开 `include_usage`），聊天 done 的 `total_tokens` 为 0，token 成本不累计——规划已接受，待后续按 provider 支持情况补 `stream_options`；流式中途回退时已推送的 partial 文本与重试答案按前缀一致假设去重（temperature=0 下成立，极端情况可能重复）。

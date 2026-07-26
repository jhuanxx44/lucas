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
- prompt：`prompts/harness/tool-loop.md`（无预算提示、无导航策略提示；该文件后更名为 `agent-loop.md`，身份与工具说明移入 `lucas-system-prompt.md`）
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
11. 剩余业务工具 eval task（web_search/stock_quote/stock_kline 的离线固定 task + 确定性 grader；wiki_recall 首版已见实验 005）
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

## 实验 005：Wiki 业务工具首轮 Eval（2026-07-20）

### 假设

在固定离线 Wiki fixture 中，当前 single Agent 能稳定使用 `wiki_recall` 完成三档任务：已索引单页事实提取、未索引页面事实提取、两个公司页面的事实综合。主要验收环境最终答案，不把“索引优先/全文 fallback”等内部路径写进 outcome grader。

### 实现

- 新增 `business-capability-v1` suite，包含 WIKI-01、WIKI-02、WIKI-03。
- 三题只授权真实生产 `wiki_recall`，使用虚构且唯一的事实与确定性 `answer_json` grader，全程禁止修改 fixture。
- 增加 fixture 可召回性测试，分别确认目标公司页、未索引公告页和两个比较页面能被生产工具发现。
- known-bad/Oracle 校验 3/3 通过，证明错误答案会失败、reference 会通过。

### 真实模型结果

当前 DeepSeek 配置、temperature=0，每题 3 trials：

| 任务 | 成功率 | 步数 | 工具调用 | 观察 |
|---|---:|---:|---:|---|
| WIKI-01 | 3/3 | 全部 2 步 | 全部 1 次 | 正确提取 97.3，但每次 observation 都带回 3 个页面 |
| WIKI-02 | 3/3 | 全部 2 步 | 全部 1 次 | 2 次只返回目标公告，1 次同时返回相似公司页 |
| WIKI-03 | 3/3 | 2/2/3 步 | 1/1/2 次 | 两次宽查询一次带回目标页与干扰页，一次分别查询两家公司 |

- 总体：9/9，19 steps，10 次工具调用。
- Token：14,127 total，平均约 1,570/run。
- 估算成本：$0.045894 total。
- 产物：`runs/business-capability-v1-20260720-202535-d8d7f0f1/`。

### 结论

1. 保留三题作为首版 Wiki 业务 smoke/capability：它们证明当前 Agent 能调用工具、理解 observation 并输出正确结构化答案。
2. 9/9 不能证明召回质量已经足够好。WIKI-01 与 WIKI-03 的稀疏 fixture 加上默认 `limit=3`，使目标页和干扰页经常被一起返回；成功部分来自候选集很小。
3. WIKI-02 是三题中区分度最好的一题，稳定证明未索引公告能被发现，但仍需增加更多数字相似的干扰公告。
4. 当前不调整任务和召回算法。后续出现区分度不足时，优先扩充干扰页、收紧相同口径和增加无答案场景，再决定是否进入文件工具 vs `wiki_recall` 的访问策略消融。

## 实验 006：Wiki 专用工具 vs 基础文件工具首轮对照（2026-07-20）

### 假设与边界

复用实验 005 的 WIKI-01～03、fixture、模型、temperature、步数和 outcome grader，只把可用工具从 `wiki_recall` 换成 `list_files + search + read_file`，观察 Agent 是否仍能完成任务以及额外成本。原 task 和 suite 不修改，filesystem-only 通过运行时覆盖形成一次性对照。

### 结果

| Variant | 成功率 | Steps | Tool calls | Tokens | 估算成本 |
|---|---:|---:|---:|---:|---:|
| `wiki_recall` | 9/9 | 19 | 10 | 14,127 | $0.045894 |
| filesystem-only | 8/9 | 38 | 29 | 33,969 | $0.100798 |

分任务结果：WIKI-01 3/3、WIKI-02 3/3、WIKI-03 2/3。filesystem-only 相比专用工具步骤翻倍、工具调用约 2.9 倍、Token 约 2.4 倍、估算成本约 2.2 倍。

唯一失败 run 中，模型先用绝对路径 `/` 调 `search` 被拒绝，随后 `list_files` 的根节点显示临时工作区目录名；模型误把该目录名再次拼进相对路径，两次读取不存在的 `lucas-eval-.../wiki/index.md`，最终触发重复失败保护。失败归因是工具 observation 的路径语义与模型路径理解，而不是 Wiki 内容缺失。

### 判分说明

首次运行时原 task 的 process grader 仍只允许 `wiki_recall`，导致原始 summary 把 filesystem 调用标成违规。正式结果基于同一批原始 9 个模型 run，用 filesystem-only 的 allowed-tools policy 重新判分；模型输出、trace 和 outcome 均未改变。中途为确认执行状态额外产生的两个 WIKI-03 run 不纳入统计。

正式产物：`runs/wiki-filesystem-only-20260720-203508-7a3bdbed/filesystem-summary.json`。

### 结论

1. 基础文件工具具备完成当前三类 Wiki 任务的能力，但效率和稳定性暂时弱于 `wiki_recall`。
2. 当前证据支持保留 `wiki_recall`，但只有三道小 fixture 任务，尚不足以决定长期架构。
3. 下一轮若继续该实验，优先修正 `list_files` 根节点展示造成的路径歧义，并扩充相似干扰页；随后重跑同一对照，区分工具 UX 缺陷与专用召回的真实收益。

## 实验 007：Wiki 关键词责任归属（jieba vs AI 显式关键词）（2026-07-20）

### 假设

当前 Agent 已经能在 tool call 中给出高质量查询，让模型直接提供结构化 `keywords[]`、工具不再使用 jieba，可能保留“公司全名、时间、指标”等完整短语，提高候选 Precision，同时保持任务成功率。

### 单变量实现

- A `jieba`：现有 `wiki_recall({query, limit})`。
- B `ai-keywords`：实验用同名 ToolSpec，协议为 `wiki_recall({keywords: string[], limit})`；工具不再分词。
- 两组共用同一索引匹配、全文评分、安全检查、页面截断、任务、fixture、模型、temperature、limit 和 grader。
- WIKI-01～03 各 3 trials，按 trial 交错运行；候选 Precision/Recall 根据 tool observation 中的页面路径确定性计算。

### 结果

| Variant | 成功率 | Steps | Tool calls | Precision mean | Recall mean | Tokens | 估算成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| jieba | 9/9 | 18 | 9 | 0.611 | 1.0 | 13,215 | $0.042130 |
| AI 显式关键词 | 9/9 | 18 | 9 | 0.500 | 1.0 | 13,706 | $0.046062 |

分任务 Precision：WIKI-01 两组均为 0.333；WIKI-03 两组均为 0.667；WIKI-02 jieba 平均 0.833，AI 显式关键词为 0.500。

AI 版确实保留了 `澄海精密`、`2025年第四季度`、`一次良率` 等短语，但模型也稳定加入 `2025`、`现金分红`、`年产能` 等宽泛词；当前评分是任一关键词命中即得分，并在索引结果不足时继续补到 `limit`，所以宽泛词让更多干扰页进入候选。WIKI-02 中 AI 版三次都返回目标公告和无关公司页，且两次额外臆造了公司名“海目星”；jieba 版两次仅用股票代码查询，只返回目标公告。

### 结论与处置

1. 假设被证伪：单独删除 jieba、把关键词责任交给 AI，没有提高成功率或候选精度，反而增加约 3.7% Token 和 9.3% 估算成本。
2. 当前主要问题不是分词，而是 `OR` 式低门槛计分和“尽量补满 limit”的返回策略；关键词越多，噪音越容易增加。
3. 产品继续保留现有 jieba 版本。仅为实验新增的 AI-keywords ToolSpec、协议和核心分支已删除，不留下未使用机制。
4. 若继续优化，下一个单变量应是候选阈值/停止补位策略，而不是再次更换关键词提取器。

实验产物：`runs/wiki-keyword-ab-20260720-210948-0b2d7985/summary.json`，包含两组完整 prompt、tool args、observation 和 trace。

## 实验 008：结果去重护栏 + 无进展强制收尾（2026-07-21）

### 背景与假设

生产聊天出现一次"分析过程中断"：模型对比博通时，用微调查询（换词序、加 Broadcom、改 limit）连续调用 `wiki_recall`/`web_search`，每次 `status=ok` 但拿回相同/相似内容（库中无博通，靠"光通信"OR 命中返回无关行业页），5 次耗尽 observation 预算后落到 `finish_reason="error"`。

**假设**：Agent 打转的本质是"反复拿回相同信息"而非"反复问相同问题"。对**结果**去重（而非对 args 去重）能抓住"换措辞查询但拿回相同内容"这类打转；命中后先回注警告让模型自纠、再次命中则强制基于已有信息收尾，可把 `finish_reason` 从 error 转为 completed，并显著降低步骤与 observation 消耗。

预期改善指标：无答案中断（error/预算耗尽）→ 正常收尾；单轮工具调用次数有界；重复的大 observation 不再进 history 回放。

### 开源调研依据

调查 LangGraph / smolagents / aider / AutoGPT / openclaw / OpenHands 真实源码（clone 读码）。关键结论：
- 只有 openclaw（`tool-loop-detection.ts`）与 OpenHands（`stuck.py`）真正做"结果/observation 去重"；其余仅有步数上限。
- 共识做法：比对 `result_hash`（非仅 args）、遍历用 `continue` 支持非紧邻重复、hash 前剥离易变字段、两档（warning→强制/拦截）、回注时给**具体替代动作**。
- 无人用语义相似度判重——精确 hash 已覆盖"换措辞"场景。
- 强制收尾（smolagents 式）对检索型任务比报错中止（LangGraph/OpenHands 式）体验更好。

### 单变量实现

只改 `harness/runner.py`，不动任何工具（工具改造留作独立实验，避免功劳混淆）：
- 维护 `seen_result_steps: {observation_hash → 首次出现的 step}`。工具**成功**后对最终 observation 文本算 sha256（我们的 observation 是纯文本、无 messageId/timestamp 等易变字段，无需字段黑名单）。
- 命中已见 hash → `stall_count += 1`，不把重复正文再塞进 history（只回注一条短提示），支持非紧邻重复。
- 两档：`stall_count==1` 回注 warning（给替代动作，放行）；`stall_count>=2`（`_STALL_FORCE_ANSWER`）回注强制收尾指令（软收尾：要求模型下一轮只出 answer，仍由模型执行）。
- 新增 trace 事件 `no_progress_detected`；新增 grader `no_stalled_progress`（断言无进展次数 ≤ 阈值）；新增固定 task `LOOP-01`（问库中不存在的公司，fixture 用"半导体"行业页复现 OR 误命中），纳入 business-capability suite。
- 同轮把 `MAX_TOTAL_OBSERVATION_CHARS` 48000→240000、`MAX_OBSERVATION_CHARS` 16000→32000（DeepSeek-V4-Flash 1M 窗口下先解除对正常复杂任务的误伤；这是独立的预算旋钮，非本实验主变量）。

### 结果（确定性层）

- 单元测试 `test_no_progress_stall_forces_answer`：baseline 复现（三次相同结果全部执行、最终非 completed）→ 改动后首次重复 warning、二次重复强制收尾、`finish_reason=completed`，two `no_progress_detected` 事件均正确追溯到首次 step。
- 全量测试 206 passed（仅需外部 model fixture 的连通性脚本除外）。修正了两个因常量调大/去重生效而过时假设的既有测试。
- `LOOP-01` oracle run 通过、known-bad run 失败，证明 grader 接受正确答案、拒绝错误答案。

**未完成（诚实标注）**：真实模型 trial 需 `DEEPSEEK_API_KEY`，当前环境无此密钥，未能跑 baseline vs 改动后的多 trial 对比（成功率/步骤/token/成本）。确定性层已证明机制正确，但"软收尾在真实模型上是否足够（模型收到强指令是否仍可能继续调工具）"尚未用真实 trial 验证。

### 结论与后续

1. 机制在确定性层成立并已进入产品链路（chat 走同一 `AgentRunner`）。
2. 待补：用真实 key 跑 `LOOP-01`（含博通式场景）多 trial，确认软收尾足够；若模型收到强指令仍打转，再升级为硬收尾（跳出工具循环、禁用工具单独发 final-answer prompt）。
3. 本护栏是第二道防线（兜底）。第一道防线（`wiki_recall` 摘要化 + 相关性阈值 + 分词级命中透明，治本，对应实验 007 预告的候选阈值方向）作为下一轮独立实验。

### 真实模型补跑（2026-07-24）

补跑边界：A=`9e4b062`（护栏前），B=`12151ce`（护栏后）；两组统一使用
`deepseek-v4-flash`、temperature=0、当前同一份 `LOOP-01` task/fixture/limits，
各 3 trials。当前环境通过同一 OpenAI-compatible 代理调用该模型，不与 7 月 20 日
历史样本混算。A 组旧 grader 不认识后来新增的 `no_stalled_progress`，因此正式比较
使用 outcome、finish reason 和原始 trace，不使用 A 组 `process_passed` 总值。

| 指标 | A 护栏前 | B 护栏后 |
|---|---:|---:|
| outcome success | 3/3 | 3/3 |
| completed | 3/3 | 3/3 |
| 平均 steps / tool calls | 2 / 1 | 2 / 1 |
| `no_progress_detected` | 0 | 0 |
| 平均 observation chars | 432 | 432 |
| 平均 prompt chars | 1,838 | 1,976 |
| 平均 tokens | 3,028 | 3,256 |
| 总成本 | $0.024638 | $0.030558 |
| 平均延迟 | 4.60s | 5.72s |

结论：本轮真实模型每次只调用一次 `wiki_recall` 就正确回答“不存在”，没有复现打转，
所以只能证明护栏没有造成功能回退，**不能证明护栏带来真实收益**。B 组多出的 prompt
说明还存在小幅固定开销，但 3 次样本不足以把 token/延迟波动归因给护栏。机制暂时保留
作为生产事故的低风险兜底，实验状态仍为“证据不足”；下一步不是继续堆 trials，而是把
原生产失败缩成一个能让 baseline 稳定出现重复 observation 的固定 task，再做同一 A/B。

产物：`/tmp/lucas-exp-runs/008-a*`、`/tmp/lucas-exp-runs/008-b*`（本机临时实验目录）。

## 实验 009：wiki_recall 摘要化（progressive disclosure）（2026-07-21）

### 假设

博通打转的根因在工具侧：`wiki_recall` 一次灌整页正文，且 OR 计分把"博通 光通信"里"光通信"蹭中的无关行业页当 `status=ok` 返回，模型读完发现不对又换词重查。把工具从"灌正文"改成"返回相关文件路径 + 一句话摘要，正文交给 read_file"（progressive disclosure），配总分阈值过滤低噪音，预期：(a) 单次 observation 体积大幅下降；(b) 模型看摘要就能判断页面是否相关，不再被无关正文误导横跳；(c) 仍能完成需要正文事实的任务（WIKI-01~03）。

### 开源调研依据

四路一手源码印证该方向是业界主流：aider repo map（返回符号摘要非正文，`repomap.py`）、Claude Code（Glob 只返路径、Read 独立且限行）、LlamaIndex `SimilarityPostprocessor` / LangChain `score_threshold`（相关性阈值过滤、宁可空返回不返回噪音、每条带分数）。关键教训：摘要用现成结构信号（frontmatter/metadata），不实时调 LLM 生成。

### 单变量实现

- `utils/wiki_core.py`：新增 `_summarize_page`（零成本：frontmatter type/tags 优先，退回正文首行截断 80 字）；`recall_wiki` 返回结构从 `{name,path,section,content,truncated}` 改为 `{name,path,section,summary}`，去掉 `max_chars`、新增 `min_score=2` 相关性门槛（低于门槛不返回，全过滤返回空列表让工具能明确说"没找到"）。
- `harness/tools/business/wiki.py`：输出改为"路径 + 摘要"列表，路径补 `wiki/` 前缀（recall 相对 wiki 根、read_file 相对工作区根，须对齐，否则 agent 拿路径 read_file 会 file not found）；spec description 说明"只返回路径和摘要，正文用 read_file 读取"。
- `prompts/harness/agent-loop.md`：补两步协作说明（recall 给地图 → read_file 取正文；摘要都不相关则据此作答，勿反复检索）。
- WIKI-01~03：`allowed_tools` 增加 `read_file`（否则摘要化后无法取正文、任务变不可解），`max_steps` 相应上调（+1~2 步给 read_file）。

### 结果（确定性层）

- 新增契约测试 `test_wiki_recall_path_is_readable_by_read_file`：recall 返回的每个路径都能被同一 workspace 的 read_file 直接读到正文——守住"给地图→取正文"链路闭合（防 wiki/ 前缀缺失）。
- 工具单测改为断言列表+摘要形态、正文不出现在召回结果里；可召回性参数化测试仍通过（`wiki/` 前缀下 `companies/...md` 仍是子串，目标页仍进候选）。
- 阈值验证：WIKI-01~03 目标页仍全部命中；查库中不存在公司（星云半导体/泸州老窖）时不再灌正文，只以摘要形式返回宽泛词蹭中的行业页，agent 可据摘要判断"非目标"。
- 全量 208 passed。

**未完成（诚实标注）**：真实模型 trial 需 `DEEPSEEK_API_KEY`，当前环境无此密钥。因此两个关键问题未用真实 trial 验证：(1) 模型能否稳定走通"recall 看摘要 → read_file 取正文"两步（纯列表形态下这是硬要求，若模型拿到列表不去 read，WIKI 任务成功率可能不升反降）；(2) 摘要形态是否真的消除博通式横跳。确定性层已证明工具契约与链路正确，但两步协作的模型侧稳定性待测。

### 结论与后续

1. 工具改造在确定性层成立并进入产品链路（chat 与 evals 共用 `recall_wiki`）。
2. 待补：真实 key 跑 WIKI-01~03 对比改造前后成功率/步骤/token（预期步骤+1~2、单步 observation 大降、总 token 下降），并跑博通式场景确认横跳消除。
3. 阈值目前是简单总分门槛：查具体公司但宽泛行业词蒙中（星云半导体命中"半导体"行业页）仍会进候选，靠摘要形态让 agent 自行判断而非靠阈值挡住。若真实 trial 显示 agent 仍被干扰，再引入"分词级命中透明"（区分度高的词必须命中）。

### 补记：`min_score` 从 2 放宽到 1（2026-07-21）

真实聊天 trace 暴露反效果：查"光通信"时，光通信板块的公司档案（光迅科技等）因分类名命中只得 1 分，被 `min_score=2` 全部过滤，agent 只好绕道 list_files 数目录。即阈值 2 不是挡噪音，而是误伤了"分类相关但名字不含关键词"的正常结果。

决定把 `min_score` 默认放宽到 1（凡关键词匹配即返回），阈值逻辑代码保留供后续复用。依据：摘要形态已足以让 agent 过滤无关页（这正是本实验的核心手段），工具端不必再卡阈值。召回质量本身（板块结构/语义相关，如"光通信"应带出全部板块公司）是更根本的问题，单列为"wiki 召回专项优化"，走独立 eval-driven（先写"查板块应召回全部 N 家公司"的召回率 task 作 baseline，再改算法），不在本实验范围。

### 真实模型补跑（2026-07-24）

补跑边界：A=`12151ce`（返回正文），B=`298cd6e`（返回路径+摘要，且包含
`min_score=1` 的最终修正）；两组统一使用 `deepseek-v4-flash`、temperature=0、当前
同一份 task/fixture/limits。WIKI-01～03 各 3 trials；另用 LOOP-01 各 3 trials 比较
无答案场景。B 组 WIKI 任务 9/9 都稳定走通 `wiki_recall -> read_file -> answer`。

#### 有明确答案的三个小 Wiki 任务

| 指标 | A 正文直返 | B 摘要后读取 |
|---|---:|---:|
| outcome success | 9/9 | 9/9 |
| 平均 steps | 2.00 | 3.33 |
| 平均 tool calls | 1.00 | 2.33 |
| 平均 observation chars | 278 | 400 |
| 平均 prompt chars | 1,898 | 4,159 |
| 平均 tokens | 3,216 | 5,829 |
| 总成本 | $0.080334 | $0.137896 |
| 平均延迟 | 4.08s | 6.75s |

两组成功率相同；B 的 tokens +81%、成本 +72%、延迟 +66%。当前 fixture 页面很短，
A 一次返回的正文平均只有 278 字，B 增加一次或两次 `read_file` 后反而更贵。因此
“摘要化会降低当前 WIKI-01～03 总上下文成本”的假设被证伪。

#### 无答案、低相关命中的 LOOP-01

| 指标 | A 正文直返 | B 只返摘要 |
|---|---:|---:|
| outcome success / completed | 3/3 | 3/3 |
| 平均 steps / tool calls | 2 / 1 | 2 / 1 |
| 平均 observation chars | 432 | 142 |
| 平均 prompt chars | 1,976 | 1,944 |
| 平均 tokens | 3,256 | 3,089 |
| 总成本 | $0.030558 | $0.024326 |
| 平均延迟 | 5.72s | 3.89s |

在模型从摘要即可判断“不是目标公司”的场景，B 无需 `read_file`，observation 减少
67%，tokens 减少约 5%，同时保持正确率。这证明 progressive disclosure 的收益是
**场景依赖**，不是对所有 Wiki 查询都成立。

阶段结论：两步协作稳定性通过（9/9），但当前小页面任务上效率显著回退；现有任务集
无法代表它原本要解决的“大页面 + 相似干扰页 + 低相关命中”问题。因此先增加一个由同一
语料派生的长页面/多干扰页固定 task，再比较正文直返与摘要后读取；若新任务仍无成功率
或总成本收益，应回滚默认摘要化，而不是继续增加召回复杂度。

#### 追加区分任务 WIKI-04

新增独立 `wiki-retrieval-experiment-v1` suite 和 WIKI-04：五个同属新材料、公司名和
指标相似的较长页面，问题只需要海岳材料一页中的资本开支。该任务不规定工具路径，使用
确定性 answer/outcome 与 forbidden-diff grader；oracle 通过、known-bad 失败。A/B 各
3 trials：

| 指标 | A 正文直返 | B 摘要后读取 |
|---|---:|---:|
| outcome success | 3/3 | 3/3 |
| 平均 steps | 2.00 | 3.33 |
| 平均 tool calls | 1.00 | 2.00 |
| 平均 observation chars | 1,904 | 833 |
| 平均 prompt chars | 3,419 | 4,673 |
| 平均 tokens | 4,093 | 6,093 |
| 总成本 | $0.031156 | $0.045990 |
| 平均延迟 | 3.70s | 5.84s |

B 确实把 observation 减少 56%，但新增模型轮次使 prompt +37%、tokens +49%、成本
+48%、延迟 +58%；其中一次还多发生一个格式 correction。成功率仍无差异。在当前
JSON-per-step loop 与模型下，“默认对所有 Wiki 查询先摘要再读正文”没有通过收益门槛。

**最终处置：回滚实验 009。** `wiki_recall` 恢复每页最多 3000 字符的正文直返，移除
强制 `wiki_recall -> read_file` prompt 和对应任务预算扩张；WIKI-04 保留在独立实验
suite，供未来 Context policy、snippet 或批量读取机制做同题对照。LOOP-01 中摘要版的
局部收益不再由默认工具契约承担，后续应通过相关性/无答案识别的独立实验解决。

产物：`/tmp/lucas-exp-runs/009-a*`、`/tmp/lucas-exp-runs/009-b*`（本机临时实验目录）。

---

## 实验 010：基于可观察信号的检索决策（2026-07-24）

### 问题与假设

产品 trace 中，用户先后询问“可以找到长鑫存储的科创板招股书原文吗”和纠正“有的”，
模型两次都未调用工具，并把“尚未上市”错误推导成“不存在招股书”；直到用户第三次明确
要求“先搜搜看”才调用 `web_search`，一次找到上交所原文。

假设：当前“模型觉得已经确知即可直接回答”的主观置信门控不可靠。改为按可观察的任务信号
触发检索——原文/链接请求、时变公司状态、否定性存在判断、用户事实纠错——可以提高检索
触发与纠错恢复率；同时保留稳定定义题直接回答，避免滑向无差别检索。

预期指标：

- RETRIEVAL-01 原文请求正确率；
- RETRIEVAL-02 用户纠错后的恢复率；
- RETRIEVAL-03 稳定定义题正确率与不必要工具调用数；
- 辅助比较 steps、tokens、成本和延迟。

### 固定任务和最小改动

- 新增独立 `retrieval-policy-experiment-v1` suite，不提前并入 regression。
- RETRIEVAL-01/02 使用冻结 Wiki 页面和唯一的上交所 URL，以 `answer_json` 确定性判卷；
  不规定内部检索路径。
- RETRIEVAL-03 用 `max_tool_calls: 0` 明确测量“稳定定义题不过度检索”；该过程行为就是本题
  要验证的策略目标。
- 新增通用 `max_tool_calls` process grader，仅补本实验所需能力。
- 生产 prompt 改为客观触发条件，并增加日期不等于事实新鲜度、用户纠错恢复、否定结论证据
  门槛和官方来源优先级。没有增加领域硬编码或代码层强制 Validator。

### Baseline 与验证状态

- 已有产品 trace baseline：RETRIEVAL-01 对应首轮失败，用户纠错对应第二轮再次失败，即已观察
  的检索触发/恢复结果为 0/2；用户第三次明确说“先搜搜看”后搜索成功。
- 三个新 task 均通过 task validation：Oracle 通过、known-bad 失败。
- Oracle suite 各 3 trials，共 9/9 通过，证明 fixture、grader 和套件编排稳定。
- 相关代码回归 107 passed。

**未完成（诚实标注）**：当前 shell 没有 `DEEPSEEK_API_KEY`，无法在同一模型、工具、环境和
预算下运行修改前后的真实多 trial。因此目前只能确认失败机制、策略改动和确定性评测闭环，
不能声称新 prompt 已提高真实模型成功率。拿到相同 provider 凭据后，应在改动前 commit 与当前
版本分别运行本 suite 每题至少 3 trials；若 RETRIEVAL-01/02 未稳定改善或 RETRIEVAL-03 出现
过度检索，再调整规则，而不是直接增加代码硬拦截。

---

## 实验 011：Planner 首次真实模型试运行与问题修复（2026-07-25）

### 背景

M3 Planner 实验的基础设施（`update_plan` 工具、SSE `plan_update` 事件、前端 PlanCard、
planner-experiment suite）完成后，用 4 个真实场景对 `deepseek-v4-flash` 进行了首次端到端
试运行。traces 保存在 `tmp/planner-traces-20260725/`。

### 4 个测试场景

| 场景 | 描述 | 结果 |
|---|---|---|
| 01-optical | 系统调研光通信行业（中际旭创/光迅科技/天孚通信），写入 wiki | 27 步，5 次 plan 更新 |
| 02-multi-query | 同时查茅台股价、比亚迪营收、宁德时代客户 | 8 步，2 次 plan 更新 |
| 03-wiki-write | 调研 AI 芯片竞争态势（英伟达/AMD/寒武纪），写报告 | 14 步，5 次 plan 更新 |
| 04-simple-compare | 对比市盈率和市净率（纯概念题） | 1 步，0 工具，0 plan ✅ |

### 发现的问题

**问题 1：先动手，后规划**

Scenario 01 和 02 中，agent 第一步就调了 `web_search`，到第 2-3 步才调用 `update_plan`。
根因：之前 prompt 中「第一步必须是 tool」规则没有为 `update_plan` 开例外，导致复杂任务
跳过了规划环节。

**修复 1**：在 `agent-loop.md` 中将「第一步规则」改为三层：
- 复杂任务：第一步 `update_plan`
- 普通查证：第一步 `wiki_recall` 或 `web_search`
- 纯寒暄/概念：直接 answer

同时在 `lucas-system-prompt.md` 的「不要在第一步就直接 answer」规则后加例外条款。

**问题 2：Plan 不忠实，行为远超计划**

Scenario 01 plan 只有 6 步，实际执行了 26 次工具调用。额外的 20 次包括重复搜索、先覆盖后
修补文件等计划外操作。

**修复 2**：在 `agent-loop.md` 和 `lucas-system-prompt.md` 中加规则：
- "计划制定后，严格按步骤执行，不要偏离计划做计划外的事"
- "如果发现计划需要调整，先调用 update_plan 更新计划，再继续执行"

**问题 3：操作顺序不合理**

Scenario 01 先写了行业对比报告（step 9），然后才开始写公司档案（step 10-11）。正常的调研
顺序应该是先收集单个公司数据，再汇总对比。

**修复 3**：在 `lucas-system-prompt.md` 的「怎么用好工具」中加：
- "操作顺序：先收集，再产出。先写单个公司档案，最后写行业对比报告"
- "修改文件前先读取：如果要修改已有文件，先用 read_file 读取，再用 apply_patch 精确替换"

**问题 4：重复成功的搜索**

Scenario 01 对同一家公司做了多次相似搜索（中际旭创 2 次、天孚通信 2 次），虽然查询词不完全
相同，但第二次搜索没有带来实质性新信息。

**修复 4**：在 `agent-loop.md` 中加规则：
- "不要重复成功的搜索：如果已经用相同或高度相似的查询词从同一来源获得了有效结果，不要再次搜索"

### 修改文件

- `prompts/harness/agent-loop.md`：重写「第一步规则」、新增「先规划再动手」「不要重复成功的搜索」规则
- `prompts/harness/lucas-system-prompt.md`：新增 update_plan 例外条款、操作顺序规则、文件修改前先读取规则、计划忠实度规则

### 下一阶段

等待修复后用相同 4 个场景重新运行，对比前后行为差异。预期改善：
- 复杂任务第一步变成 `update_plan` 而非直接搜索
- 总步数下降（plan 忠实度提高）
- 不再出现先写报告再写档案的倒序操作

### 回归测试（2026-07-25，修复后重新运行）

用相同 4 个场景重新运行，对比修复前后：

| 场景 | 修复前 steps | 修复后 steps | 变化 | 修复前 first=plan | 修复后 first=plan |
|---|---|---|---|---|---|
| 01-optical | 27 | 17 | **-37%** | ❌ | ❌ (仍先搜索) |
| 02-multi-query | 8 | 6 | -25% | ❌ | ✅ |
| 03-wiki-write | 14 | 10 | **-29%** | ✅ | ✅ |
| 04-simple-compare | 1 | 1 | 0 | N/A | N/A |

总步数从 50 降到 34（-32%），总工具调用从 45 降到 29（-36%）。所有场景 0 次 invalid output。

**scenario-01 仍不先从 plan 开始**：模型连续做了 4 次 web_search 后才在第 5 步调用
`update_plan`。这暴露了「复杂任务」与「普通查证」的边界对模型不够明确。追加修复：将
第一步规则中的「复杂任务」定义改为具体可判断的条件（需要写入文件 / ≥2 家公司 / 多阶段
流程 / 指令关键词）。

### 决策修正（2026-07-25）：撤销「第一步强制 plan」

回归分析后发现，scenario-01 模型的行为是「侦察 4 步 → plan → 执行 11 步」，
这本身就是合理的探索策略。强制第一步 must-be-plan 是在框死不该框死的行为。

撤销了 `agent-loop.md` 中的「复杂任务第一步必须是 update_plan」规则，
改为「允许先做 1-3 步侦查，再规划」。保留的规则：
- 最后一步必须 answer
- 操作顺序：先收集再产出
- 每完成一个阶段更新计划
- 不要重复成功的搜索

---

## 2026-07-26 BM25 检索对照实验

- **报告**: `2026-07-26-BM25检索对照实验.md`
- **commit**: `32e90a9`
- **结果**: TF-IDF > BM25（46 篇小语料），R@5: 0.650 vs 0.542
- **参数**: BM25 b=0.75 为最优，降低文档长度惩罚无益
- **关键发现**: 小语料上 IDF 主导，BM25 优势需 200-500+ 篇才能体现

## 2026-07-26 LLM 关键词 vs jieba 分词检索对照实验

- **报告**: `2026-07-26-LLM关键词检索对照实验.md`
- **commit**: `bdf8e17`
- **结果**: LLM 关键词 R@5=0.691，jieba R@5=0.479（**+0.212**）
- **模型**: DeepSeek-Chat 实时提取，15 次零失败
- **关键发现**: LLM 分词碾压 jieba 的根本原因不是分词算法，而是 LLM 能填平"自然语言→检索关键词"的语义鸿沟（实体识别、概念展开、领域判断）
- **对照**: 人工关键词 R@5=0.771（BM25）/ 0.882（TF-IDF），LLM 尚有 0.08 差距
- **行动**: 删除生产链路中 jieba NL 路径，`recall_wiki` 改为纯关键词模式

# Lucas Context 管理多阶段规划（从简单到复杂）

日期：2026-08-01
状态：阶段 1 已实现（5.2 配置与预估、5.3 压缩策略、5.4 UI 表现 + 注入测试）；真实模型
  初步验证已完成（10 run，见 `docs/experiments/2026-08-01-context-compression-v1.md`）：
  机制可触发、简单任务零差异，但 12K trigger 窗口下高频压缩导致 token 反升 +23%，
  trigger 参数待调（提高窗口 / keep_recent_steps=2 / 补 CTX 长任务）。
  2026-08-01 设计定稿并实现：软线触发语义改为"当前用户轮次全程保留"；新增
  开始时超线（初始预估，超硬线拦截不提交）+ 硬线 0.95（整轮 FIFO 兜底），
  见 5.3（注入测试 33 passed，含初始拦截/软线区间/fifo 整轮删除）
对应路线图：Phase 4（Context 选择与一次摘要压缩）的实施路径

## 1. 背景与目标

Responses 原生迁移后，Lucas 的 Runner 已采用**全量消息回放**：每轮把上一轮完整
`response.output` items 与 `function_call_output` 显式追加进 `context.input_items`
（见 `harness/runner.py` 的 `_append_function_output`），模型可以看到自己说过的话和
全部工具结果。

已知代价是**长任务输入 token 显著上升**，已有证据：

| 证据 | 数值 |
|---|---|
| PLAN-01 平均（Responses 迁移后，3 trial） | 19 steps、138,192 tokens、$0.347348 |
| PLAN-01~04 并发 Pilot（每题 1 trial） | 78 steps、448,941 tokens、$1.541422 |
| PLAN-01 token 对比迁移前 baseline | +102.6% |
| PLAN-01 步数 | 正好用满 20-step 上限 |

目标不是复刻 Codex 的 ContextManager（那是多线程、多 agent、热更新环境下的复杂实现），
而是针对 Lucas 的真实情况——**单 Agent、串行工具、投研长任务、DeepSeek Responses**——
用最少的代码省下 token 成本且不伤成功率。整条路径只分三个阶段，**前期只做阶段 1**；
每一阶段有独立验收和决策门，简单版本达标就停，不往上走。

## 2. 现实情况与真实需求

- **使用场景**：单 Agent 分析任务（wiki 检索、多公司对比、知识库更新），典型长任务是
  PLAN-02/04 这类多来源、多文件、多步骤任务；上下文大头来自早期工具结果与模型自身输出。
- **现状机制**：只有 `MAX_OBSERVATION_CHARS = 10_000_000` 的失控截断；`RunLimits` 没有
  上下文预算字段；每步提交前不做任何选择；trace 有 `model_input_prepared`
  （input_items 数 / input_chars）与 `observation_chars`，但没有选择/省略事件。
- **已有基建（5.2 可直接复用）**：每轮真实 usage 采集链路完整——`utils/llm_client.py`
  的 `responses_usage()` 解析真实 `usage.input_tokens/prompt_tokens`，
  `harness/model_adapter.py` 写入 `ModelTurn.usage`，runner 累计 `total_usage` 并记入
  trace `model_call_finished`；1M 窗口上限已硬编码在 `server/services/agent_stream.py`
  的 `_CONTEXT_LIMIT_TOKENS`，仅服务前端 context 圆环（`context_usage` SSE），
  Runner 不知情、不可配置。
- **已具备**：全量回放、call_id 配对、工具结果写回历史、usage 与成本统计、冻结的
  baseline（`deepseek-v4-flash`、temperature=0、固定 prompt 哈希、固定 task/grader）。
- **真实需求优先级**：先解决"长任务 token 成本高"这个已证实的问题；再谈"更聪明的
  上下文选择"；最后才考虑摘要压缩。**没有证据表明 Lucas 需要 Codex 级的上下文机制。**

## 3. 设计原则

从 Codex 的 ContextManager 提炼出三条与 Lucas 现状匹配的原则，其余复杂能力全部延后：

1. **结构完整（配对不变量）**：省略不能留下悬空的 `function_call` 让模型误以为有结果
   ——要么 call 与 output 成对丢，要么在丢 output 的位置回写占位说明。无论如何，
   Responses 协议结构必须完整。
2. **省略必须可见**：被省略的内容回写一行说明，明确告诉模型"该步骤已执行、结果因
   上下文压缩被丢弃"（如"第 N 步 {tool} 工具结果因压缩被丢弃，约 X token；该步骤已
   执行，回答时请勿假设其内容"），避免模型误以为工具失败或结果为 null，也防幻觉引用。
3. **策略可预期、可归因**：每次省略都在 trace 记录 before/after 与丢弃范围；具体策略
   （保留最近 N 步、挖空 tool output、还是从头整步丢弃）由实验数据决定，第一版采用
   "保留最近一步 + 丢弃更早 tool output"。

## 4. 三阶段路径

| 阶段 | 做什么 | 复杂度 | 何时做 | 主要产物 |
|---|---|---|---|---|
| 1 | 成本画像 + token 预算压缩 | 最低 | 前期主攻 | 画像报告 + 轻量 token 预估 + 保留最近一步、丢弃更早 tool output |
| 2 | 结构化选择与归因 | 低 | 阶段 1 有效且需要更细解释 | ContextManager、保留窗口、trace 事件 |
| 3 | 摘要压缩与 Codex 级能力 | 高 | 阶段 2 仍不足且有证据 | summary 覆盖；其余不主动实现 |

每阶段结束都回答三个问题：**省了多少？成功率掉没掉？能归因吗？** 达标就停，只有
出现明确证据才进入下一阶段。

## 5. 阶段 1：成本画像 + token 预算压缩（前期主攻）

目标：先查账，再用最少的代码验证"超预算时只保留最近一步、丢弃更早工具结果"是否有效。

### 5.1 成本画像（不改代码）

- 用现有 runs 的 trace/artifact（PLAN-01/02/04、WIKI-04），统计每步 `input_items` 构成：
  assistant 消息、function_call_output、user 指令各占多少字符/token；画出 token 随步数
  增长曲线，找出"大头"。
- 验证方式：产出画像表 + 归因结论。
- 决策门：若现有任务根本不超预算，先补 CTX 候选任务再继续；若大头是模型自身长输出，
  阶段 1 的丢弃顺序要调整（先丢早期 assistant 消息而非工具结果）。

### 5.2 token 计算器与触发时机

- **不做完整版 token 计算器（不需要 tiktoken）**：API 每轮已返回真实
  `usage.prompt_tokens`，且超窗请求会在提交时报错，必须"提交前预估"而非事后计量。
- **已具备（复用，不再实现）**：真实 usage 采集链路（见第 2 节"已有基建"）；
  提交前可观测本轮 `input_items` 数与 `input_chars`（`model_input_prepared`），
  与每步真实 `prompt_tokens` 构成系数校准所需的历史数据对。
- **待实现 1：配置化窗口**。`lucas.yaml` 新增 `model_context_window`（V4-Flash 默认
  1M，可覆盖）并传入 Runner；`server/services/agent_stream.py` 的
  `_CONTEXT_LIMIT_TOKENS` 改为引用同一配置或由调用方同步，避免两处口径漂移。
- **待实现 2：提交前轻量预估**。`下一轮预估 = 上一轮真实 prompt_tokens + 本轮新增
  items 字符 × 系数`；系数用最近几轮真实 usage 与字符数的比值动态校准，不重新编码
  全部历史。
- **待实现 3：触发时机**。必须"预判"而非"事后发现"：超窗请求 API 会直接报错，
  因此每步提交前估算 `输入 + 预留输出空间 > 窗口 * 0.9` 时先压缩再提交。未超阈值时
  提交内容与 baseline 逐字节一致，简单任务零行为差异。

### 5.3 简单版压缩策略

- **当前用户轮次全程保留（压缩边界 = 用户轮次）**：step 0（初始 user 消息，含
  历史渲染与当前问题）与最近 `keep_recent_steps`（默认 1，可配置）步的 react 过程
  （LM 思考 + 工具调用 + 工具结果）全量保留——"从最近的用户提出要求到 LM 处理的
  中间过程"不压缩；压缩对象是**这轮提问之前**的更早 step。多轮历史仍走
  `_render_history` 文本渲染（有 `_HISTORY_TURNS` 限制），不单独压缩。
- **开始时超线（初始预估）**：第一轮提交前无上一轮真实 usage，需用初始 user
  消息字符数 × 系数估算；若初始预估 + 预留输出 > 窗口 × 0.9，先压缩再提交，不直接
  把超线请求发给 API。
- **plan 永不压缩**：`update_plan` 的 `function_call`（参数含计划全文）与
  `function_call_output`（计划回显）标记为不可压缩，压缩时跳过——plan 是任务级状态，
  任务全程需持续可见，丢失会导致模型遗忘计划（路线图 Phase 2 已记录此坑）。其体积很小
  （真实 case 38 次累计 6.7K 字符），全部保留无成本问题。
- **reasoning 平时保留、压缩时丢弃**（对齐 Codex）：未压缩时 reasoning 作为 API 消息
  每轮回传（与现状一致，模型可引用自己之前的推理）；触发压缩时，更早步骤的 reasoning
  全部丢弃——Codex 压缩时同样把 Reasoning 列入丢弃名单，其知识只通过总结间接保留；
  我们阶段 1 无总结，直接丢弃，省 12–18% 的重复成本。
- 每个被丢的 tool output 位置**回写占位说明**，明确"该步骤已执行、结果因压缩被丢弃、
  约 X token，回答时请勿假设其内容"，避免模型误以为工具未执行或结果为 null，也防幻觉
  引用。
- **软线兜底（pass2）**：挖空更早 tool output 后仍超 0.9 线 → 继续从最早丢弃
  assistant message / reasoning 直到不超或无可丢；单条 output 超过硬上限的单独截断
  （复用现有截断逻辑）。
- **硬线（0.95，无条件兜底）**：软线压缩后 `预估 > 窗口 × 0.95`（意外情况：软线
  压不住或估算偏差）→ 从最早 step 开始**整轮 FIFO** 删除（reasoning + function_call
  + function_call_output + message 成对丢，结构天然完整），直到 `预估 ≤ 0.95 × 窗口`
  或只剩 step 0。step 0（初始 user 消息）与 system prompt（`ModelRequest.instructions`，
  本就不在 input_items 中）永不丢。95% 即有效窗口，5% 余量给输出与估算误差，语义同
  Codex effective window。trace/SSE 事件带 mode（soft/fifo）与 dropped_steps。
- 每次超阈值都触发（可多次压缩），不限制一 run 只压一次；trace 记录每次压缩的时间点、
  before/after 估算 token、丢弃的 step 列表。
- **已知取舍**：软线挖空不是从头截断，前缀不稳定（早期 assistant 消息保留、工具
  结果被挖空），prefix cache 命中打折，但省 token 更多（tool output 通常是最大头）；
  硬线整轮 FIFO 才保证结构完整。第一版接受软线取舍，由实验数据决定软线是否也改为
  整步丢弃。
- 验证方式：注入测试（构造超预算 items 断言保留窗口、丢弃范围、占位说明）；全量测试
  不回归；在冻结 baseline 上跑 PLAN-01/02/04、WIKI-04 与简单回归（READ-02、LOOP-01）
  各 ≥3 trials，对比 success_rate / prompt_tokens / cost / steps。
- 决策门：`prompt_tokens` 显著下降（参考目标 ≥20%）且成功率不降 → 达标即停；
  成功率下降 → 提高窗口阈值或保留更多最近步骤，或放弃并记录失败案例。

### 5.4 压缩的 UI 表现（补充需求）

压缩是后台机制，但触发时用户应可感知、可归因。表现分三层，全部复用同一条 runner
事件，不新增复杂状态。

- **事件协议**：runner 每次压缩后推送 `on_event({"kind": "context_compressed",
  step, before_estimated_tokens, after_estimated_tokens, freed_tokens,
  dropped_steps})`，trace 同步记录（5.3 已要求）；产品聊天链路
  （`server/services/agent_stream.py`）转发为 SSE `context_compressed`。eval 直跑
  runner 时该事件只进 trace，无前端表现——UI 不接入实验路径。
- **输入框 Context 圆环**（`web/src/components/ChatInput.tsx`）：压缩发生时圆环做
  一次脉冲高亮并短暂显示压缩徽标；随后真实 `prompt_tokens` 回退、环缩小——用户看到
  回退不会误以为是数据错误。tooltip 追加最近一次压缩摘要（第 N 步、丢弃 X 步、
  释放约 Y tokens）。
- **步骤列表**（AnalysisProcess 与 TracePanel 共用 `ChatTraceStep`）：新增
  `kind: "compression"` 步骤，label 如"上下文压缩：丢弃 12 步工具结果，释放约
  98K tokens"，写入该轮消息的 `traceSteps`——消息完成后持久化，Trace 面板与导出
  JSON 可见（可归因）。
- **Trace 事件明细**：`context_compressed` 进入 `runtimeTrace`，dropped_steps 与
  before/after 在事件层可见；UI 不展开明细，避免拥挤。
- **取舍**：不做 toast/通知中心，不打断用户；给模型的占位说明文案与 UI 摘要文案
  分离（前者进模型上下文，后者面向用户）；UI 只展示步数与释放量，明细留给 trace。

## 6. 阶段 2：结构化选择与归因（可选增强）

仅在阶段 1 达标且需要"更精细、可解释"时才做；如果阶段 1 已满足需求，本阶段可以只做
归因增强，不复杂化规则。

- 引入 `harness/context.py`：`ContextItem`（最小字段：id、source、step_id、compressible、
  estimated_tokens）、`ContextSelection`（selected/dropped/before/after/reason）。
- 80% 预算阈值触发；保留最近 N 步（与阶段 1 的 `keep_recent_steps` 一致，默认 1，
  可配置）；其余按阶段 1 的策略丢弃。
- trace 事件升级为 `context_candidates` / `context_selected`，带 `history_version`
  （每次省略后递增），replay 可还原"省略后历史长什么样"。
- 按需补发送前规范化：给缺失输出的 call 补 output、移除没有 call 的 orphan output
  （无真实案例则不做）。
- 验证方式：选择规则单测；对照实验（baseline vs 阶段 1 vs 阶段 2）报告三档对比。
- 决策门：阶段 2 相比阶段 1 的成功率、token、成本没有显著改善，就保留阶段 1 的简单
  实现，不为了"更完整"而升级。

## 7. 阶段 3：摘要压缩与 Codex 级能力（不主动实现）

- **摘要压缩**：触发条件——阶段 1-2 的丢弃导致成功率下降，且 trace 证明是"必要信息被
  丢弃"而非其他原因；此时才用 LLM 把最早可压缩内容合并成一段摘要（`llm-weight: light`），
  每 run 最多一次，保留 covered item ids。验证：压缩事件 + 事实可追溯（摘要事实能定位
  到原始 observation）。对齐 Codex 内联压缩：完整历史（含推理）作为总结输入，压缩后
  新历史只保留最近用户消息 + 总结，推理/工具调用/输出/助手消息全部不保留，
  `history_version` 递增。决策门：压缩成功率不低于丢弃版且 token 更低 → 保留，否则删除。
- **Codex 级能力**：StepContext 不可变快照、world-state diff、reference baseline、
  前缀缓存调优、并行工具有序提交、在线 compact continuation、多 agent 共享 runtime——
  这些是 Codex 在多线程/热更新/多 agent 约束下的产物，Lucas 单 Agent 串行执行没有对应
  需求。仅当出现以下信号之一才单项评估（单变量对照，不整套搬入）：
  - 引入多 agent / subagent；
  - 需要用户 steer 或热更新工具/MCP；
  - 长任务在线省略出现"模型状态丢失"的证据。

## 8. 实验与记录规范（所有阶段通用）

- 对照固定项：同一 Runner、模型（`deepseek-v4-flash`）、temperature=0、冻结 prompt
  哈希、同一 task/grader 与预算。
- 每档每题 ≥3 trials，交错运行；报告分布与失败样本，不只看均值。
- 报告写入 `docs/experiments/`，日志追加 `docs/experiments/experiment-log.md`；结论
  明确写"保留 / 缩小范围 / 删除"及证据。
- `raw/` 不变；全量后端测试不回归；新机制不接入产品路径，除非实验证明收益。

## 9. 主要风险

| 风险 | 控制 |
|---|---|
| 丢弃必要信息导致成功率下降 | 上限先设高值（保守），失败样本人工抽查；按失败案例调整 |
| 简单任务被误触发 | 未超限零行为差异；READ-02 / LOOP-01 回归验证 |
| 省略后模型幻觉引用 | 省略说明回写 + 检查回答是否引用已省略步骤 |
| token 估算不准导致触发时机漂移 | 字符折算 + 每轮真实 usage 校准；报告 before/after 实际 token |
| 过早引入复杂机制 | 三阶段决策门；阶段 1 达标即停，不追求 Codex 级完整性 |

## 10. 结论一句话

先用最便宜的"超限丢最早"验证方向，省到钱且不伤成功率就停；只有出现真实证据才逐级
往上走，Codex 的完整 ContextManager 不在 Lucas 当前的需求范围内。

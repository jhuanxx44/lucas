# Lucas Context 管理多阶段规划（从简单到复杂）

日期：2026-08-01
状态：规划草案，待实施
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

本规划的目标不是复刻 Codex 的 ContextManager（那是多线程、多 agent、热更新环境下的
复杂实现），而是针对 Lucas 的真实情况——**单 Agent、串行工具、投研长任务、DeepSeek
Responses**——设计一条从简单到复杂的渐进路径，**前期只做最简单的版本**：用最少的
代码省下 token 成本，且不伤成功率。每一阶段都有独立验收和决策门，简单版本达标就停，
不往上走。

## 2. 现实情况与真实需求

- **使用场景**：单 Agent 分析任务（wiki 检索、多公司对比、知识库更新），典型长任务是
  PLAN-02/04 这类多来源、多文件、多步骤任务；上下文大头来自早期工具结果与模型自身输出。
- **现状机制**：只有 `MAX_OBSERVATION_CHARS = 10_000_000` 的失控截断；`RunLimits` 没有
  上下文预算字段；每步提交前不做任何选择；trace 有 `model_input_prepared`
  （input_items 数 / input_chars）与 `observation_chars`，但没有选择/省略事件。
- **已具备**：全量回放、call_id 配对、工具结果写回历史、usage 与成本统计、冻结的
  baseline（`deepseek-v4-flash`、temperature=0、固定 prompt 哈希、固定 task/grader）。
- **真实需求优先级**：先解决"长任务 token 成本高"这个已证实的问题；再谈"更聪明的
  上下文选择"；最后才考虑摘要压缩。**没有证据表明 Lucas 需要 Codex 级的上下文机制。**

## 3. 设计原则

从 Codex 的 ContextManager 提炼出三条与 Lucas 现状匹配的原则，其余复杂能力全部延后：

1. **配对不变量**：`function_call` 与对应 `function_call_output` 必须成对保留或成对丢弃，
   丢弃不能破坏 Responses 协议结构。
2. **前缀单调**：省略只从最早的内容开始，被省略的历史不再回到上下文，新内容只往末尾
   追加。行为可预期，且稳定前缀有利于 provider 端缓存。
3. **省略必须可见**：被省略的内容回写一行摘要说明（如"已省略第 N 步工具结果，约 X
   token"），避免模型幻觉式引用不存在的步骤。

**明确不做（长期）**：world-state diff、reference baseline、prefix-cache 调优、
StepContext 不可变快照、并行工具 ordered 提交、在线 compact 的 continuation 语义、
多 agent 共享 runtime——这些是 Codex 在多线程/热更新/多 agent 场景下的必要复杂度，
Lucas 单 Agent 串行执行暂时用不上。只有出现对应真实需求（如多 agent、实时 steer）时
才评估单项，不整套实现。

## 4. 多阶段路径总览

| 阶段 | 做什么 | 复杂度 | 触发条件 | 主要产物 |
|---|---|---|---|---|
| 0 | 上下文成本画像 | 无代码 | 立即 | 画像报告，确认问题位置 |
| 1 | 最小硬上限截断 | 最低 | 画像确认超预算 | `max_context_tokens` + 整步成对丢弃 |
| 2 | 结构化选择与归因 | 低 | 阶段 1 有效且需要归因 | ContextManager、trace 事件、保留窗口 |
| 3 | 规范化（配对修复） | 低 | 出现 orphan/配对问题 | `for_prompt` 规范化 |
| 4 | 一次摘要压缩 | 中 | 阶段 1-3 丢弃伤成功率且是信息损失所致 | summary 覆盖机制 |
| 5+ | Codex 级能力 | 高 | 出现多 agent/热更新等真实需求 | 单项评估，不整套实现 |

每阶段结束都回答三个问题：**省了多少？成功率掉没掉？能归因吗？** 达标就停在当前
阶段，只有出现明确证据才进入下一阶段。

## 5. 阶段 0：上下文成本画像（不改代码）

- 用现有 runs 的 trace/artifact（PLAN-01/02/04、WIKI-04），统计每步 `input_items` 构成：
  assistant 消息、function_call_output、user 指令各占多少字符/token；画出 token 随步数
  增长曲线，找出"大头"。
- 验证方式：产出画像表 + 归因结论。
- 决策门：若现有任务根本不超预算，先补 CTX 候选任务再继续；若大头是早期工具结果，
  阶段 1 按"先丢最早的整步"；若大头是模型自身长输出，调整丢弃顺序（先丢早期
  assistant 消息）。

## 6. 阶段 1：最小硬上限截断（前期主攻的"简单版本"）

目标：用最少代码实现"超预算就从最早处省略"，验证丢弃方向是否有效。

- `RunLimits` 新增可选 `max_context_tokens`（0 或 None 表示不限制，兼容现有任务）。
- 每步提交前估算输入 token（字符数折算，用上一轮真实 `usage.prompt_tokens` 校准），
  超过上限时从最早的整步开始成对丢弃（`function_call` + `function_call_output`），
  直到不超；回写省略说明行。
- 不引入 ContextItem、不做保留窗口、不做 80% 阈值——**超限才丢，丢最早**。
- 未超限时提交内容与 baseline 逐字节一致，简单任务零行为差异。
- trace 新增 `context_omitted` 事件：丢弃了哪些 step、before/after 估算 token。
- 验证方式：注入测试（构造超预算 items 断言丢弃顺序、成对性、省略说明）；全量测试
  不回归；在冻结 baseline 上跑 PLAN-01/02/04、WIKI-04 与简单回归（READ-02、LOOP-01）
  各 ≥3 trials，对比 success_rate / prompt_tokens / cost / steps。
- 决策门：`prompt_tokens` 显著下降（参考目标 ≥20%）且成功率不降 → 达标，停在阶段 1
  或进入阶段 2 补归因；成功率下降 → 缩小丢弃范围（提高上限）或放弃，记录失败案例。

## 7. 阶段 2：结构化选择与归因（可选增强）

仅在阶段 1 达标且需要"更精细、可解释"时才做；如果阶段 1 已满足需求，本阶段可以只做
归因增强，不复杂化规则。

- 引入 `harness/context.py`：`ContextItem`（最小字段：id、source、step_id、compressible、
  estimated_tokens）、`ContextSelection`（selected/dropped/before/after/reason）。
- 80% 预算阈值触发；保留最近 2 步 + 当前步；其余按阶段 1 的顺序丢弃。
- trace 事件升级为 `context_candidates` / `context_selected`，带 `history_version`
  （每次省略后递增），replay 可还原"省略后历史长什么样"。
- 验证方式：选择规则单测；对照实验（baseline vs 阶段 1 vs 阶段 2）报告三档对比。
- 决策门：阶段 2 相比阶段 1 的成功率、token、成本没有显著改善，就保留阶段 1 的简单
  实现，不为了"更完整"而升级。

## 8. 阶段 3：规范化（配对修复，按需）

- 把"成对丢弃"升级为发送前规范化：给缺失输出的 call 补 output、移除没有 call 的
  orphan output、工具输出硬上限截断统一收口。
- 触发条件：trace 或测试中出现 orphan output / 缺失 output 的真实案例；没有案例就不做。
- 验证方式：配对不变量测试。

## 9. 阶段 4：一次摘要压缩（路线图 compression，可选）

- 触发条件：阶段 1-2 的丢弃导致成功率下降，且 trace 证明是"必要信息被丢弃"而非其他
  原因；此时才用 LLM 把最早可压缩内容合并成一段摘要（`llm-weight: light`），每 run
  最多一次，保留 covered item ids。
- 验证方式：压缩事件 + 事实可追溯性检查（摘要中的事实能定位到原始 observation）。
- 决策门：压缩成功率不低于丢弃版且 token 更低 → 保留；否则删除，退回丢弃方案。

## 10. 阶段 5+：Codex 级能力（不主动实现）

对应 Codex ContextManager 的复杂能力（StepContext 不可变快照、world-state diff、
reference baseline、前缀缓存调优、并行工具有序提交、在线 compact continuation、多
agent 共享 runtime）。这些是 Codex 在"多线程、热更新环境、多 agent"约束下的必然产物；
Lucas 单 Agent 串行执行**没有对应真实需求**。仅当出现以下信号之一才评估单项：

- 引入多 agent / subagent；
- 需要用户 steer 或热更新工具/MCP；
- 长任务在线 compact 出现"省略后模型状态丢失"的证据（此时评估 continuation 语义）。

评估时单变量对照，不整套搬入。

## 11. 实验与记录规范（所有阶段通用）

- 对照固定项：同一 Runner、模型（`deepseek-v4-flash`）、temperature=0、冻结 prompt
  哈希、同一 task/grader 与预算。
- 每档每题 ≥3 trials，交错运行；报告分布与失败样本，不只看均值。
- 报告写入 `docs/experiments/`，日志追加 `docs/experiments/experiment-log.md`；结论
  明确写"保留 / 缩小范围 / 删除"及证据。
- `raw/` 不变；全量后端测试不回归；新机制不接入产品路径，除非实验证明收益。

## 12. 主要风险

| 风险 | 控制 |
|---|---|
| 丢弃必要信息导致成功率下降 | 从最保守上限开始（如 max_context_tokens 先设高值），失败样本人工抽查；按失败案例调整 |
| 简单任务被误触发 | 未超限零行为差异；READ-02 / LOOP-01 回归验证 |
| 省略后模型幻觉引用 | 省略说明回写 + 检查回答是否引用已省略步骤 |
| token 估算不准导致触发时机漂移 | 字符折算 + 每轮真实 usage 校准；报告 before/after 实际 token |
| 过早引入复杂机制 | 每阶段决策门；阶段 1 达标即停，不追求 Codex 级完整性 |

## 13. 结论一句话

先用最便宜的"超限丢最早"验证方向，省到钱且不伤成功率就停；只有出现真实证据才逐级
往上走，Codex 的完整 ContextManager 不在 Lucas 当前的需求范围内。

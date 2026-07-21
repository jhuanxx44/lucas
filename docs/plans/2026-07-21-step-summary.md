# 计划：用「模型生成的步骤摘要」替代原始 reasoning 草稿展示

## 背景与问题

聊天区过程展示当前显示的是模型的**原生 reasoning 通道**（`reasoning_content`，见
`utils/llm_client.py:295`、`harness/runner.py:319`）。这是模型的思维草稿：每一轮
ReAct 循环都把完整 `{instruction}+{observations}` 重新喂给无状态的模型，模型每步都
从「我们被问到 X…需要对比…」重新热身，因此 trace 里每段思考开头高度雷同、冗长。

Codex 等工具展示的不是草稿，而是模型**另外生成的、面向用户的一句话摘要**（「我会把
这根线做成双轴趋势图…」「测试 68/68 通过…」）。观感差异的根因是：草稿 vs 成品。

用户已确认方向：**路线 B —— 让模型每步产出简短摘要，聊天区只显示摘要，丢弃原始草稿。**

## 假设与指标（eval-driven）

这属于 CLAUDE.md 定义的 Agent 机制实验（Loop/Trace + 输出契约变更），走 eval 流程。

- 假设：要求模型每步额外输出一句面向用户的 `summary`，并用它替代原始 reasoning 展示，
  能显著提升 trace 可读性，且**不损害任务成功率**。
- 主指标（outcome）：business-capability 套件成功率相对 baseline 不回归。
- 次指标：平均步数、成本、summary 出现率（覆盖度）。
- 验收以环境最终状态（answer_json grader）为准，trace 仅用于解释。

## 方案

### 1. 输出契约：在 action JSON 增加可选 `summary` 字段
`prompts/harness/agent-loop.md`：
- tool 与 answer 两种 JSON 均新增可选字段 `summary`：一句给用户看的话，说明「这一步在
  做什么/发现了什么」，简短、不复述任务前提、不含内部术语。
- 明确要求 `summary` 放在 JSON 首个字段。
- 强调 `summary` 是给人看的旁白，真正的动作仍由 `action`/`tool`/`reply` 决定。

`summary` 对解析零风险：`_parse_action`（`harness/runner.py:363`）只读
`action/tool/args/reply`，忽略未知字段；`AnswerStreamParser` 的正则只认 `"reply":`
与 `"action":"tool"`，前置的 `summary` 不影响判定。

### 2. Runner：解析并发出 summary 事件
`harness/runner.py`：
- `_parse_action` 额外提取 `summary`（可选 str），随 action dict 返回。
- 主循环在解析出 action 后、**执行工具前**，若有 summary 且 `on_event` 存在，发出
  `{"kind":"summary","step":step,"text":summary}`。answer 分支同样在返回前发出。
- 纯增量，不改任何终止/预算/重试语义；eval 非流式路径也会解析到 summary（但 eval 不
  消费 on_event 的 summary，无副作用）。

### 3. SSE 桥：转发 summary，停止转发 thought
`server/services/agent_stream.py`：
- `_forward` 新增 `kind=="summary"` → SSE `summary` 事件 `{step,text}`。
- 移除 `kind=="thought"` 的转发（原始草稿不再进前端）。runner 内部仍产生 reasoning，
  仅在 SSE 层丢弃；trace 文件仍完整记录，调试可查。

### 4. 前端：展示 summary，移除 thought 展示
- `web/src/types/index.ts`：`ChatTraceStep.kind` 增加 `"summary"`（保留 `thought`
  类型定义以兼容历史消息，但新链路不再产生）。
- `web/src/hooks/useChat.ts`：新增 `case "summary"` → 追加一条
  `{kind:"summary", label:text}` trace step；移除/停用 `case "thought"`。
- `web/src/components/AnalysisProcess.tsx`：`summary` 步渲染为**醒目正文**
  （zinc-600，非斜体），tool/action 步维持灰色小字（Codex 版式：摘要在上、动作在下）。
  历史消息里的 `thought` 步仍按旧灰色斜体渲染，不破坏老会话。

### 5. Eval 验证
1. baseline：`python -m evals.harness run-suite business-capability --agent lucas-single --trials 3`
2. 实现 1–4 后，同命令跑 variant 3 trials。
3. 对比成功率/步数/成本/summary 覆盖率。成功率回归则回退契约改动，只保留前端兜底。
4. 结论记入 `docs/learnings/2026-07-21-步骤摘要.md`（含 baseline vs variant 数据）。

## 风险与权衡

- **行为风险**：要求每步写 summary 会让模型多articulate意图，可能微调其规划路径。用 eval
  三试对比成功率兜底；回归即回退。
- **成本**：每步多几十 token 的 summary，成本增量极小，eval 会量化。
- **兼容**：历史消息仍走 `thought`/`processSteps` 兜底渲染，不破坏。
- **前置依赖**：eval 需真实模型 API key。若当前环境无 key，我会实现代码 + 单测，并把
  eval 命令交给你在有 key 的环境跑；不假装跑过。

## 不做

- 不流式逐字推送 summary（短文本，解析后整条发出即可，避免 AnswerStreamParser 增复杂度）。
- 不改 reasoning 通道本身（模型原生思考保留，仅不展示）。
- 不动工具执行、预算、超时、重试等代码语义层。

## 验证清单

- [ ] `pytest`（runner 解析 summary、SSE forward 的既有单测不破，新增最小单测）
- [ ] `cd web && npm run build` 通过
- [ ] eval baseline vs variant 三试对比（或交付命令由用户跑）
- [ ] 手动：聊天区每步显示简短摘要，无原始草稿；历史会话不破

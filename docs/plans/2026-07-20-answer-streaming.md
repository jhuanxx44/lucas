# Answer 阶段逐 token 流式规划

日期：2026-07-20
状态：已执行
来源：backlog #1（docs/harness/experiment-log.md 实验 003）

## 1. 目标与非目标

**目标**：聊天链路中，模型产出最终答案时逐 token 推送到前端（恢复旧 manager 的流式体验），而不是整段一次性 `synthesis_chunk`。

**非目标**：
- 工具步骤（JSON action）不流式——协议要求完整 JSON 才能解析，维持缓冲。
- 不改 evals 行为：评测路径继续走非流式 `complete()`，grader 看到的 answer 不变。
- 不改 prompt 模板与输出契约：模型仍输出 `{"action":"answer","reply":"..."}` JSON。

## 2. 方案：增量 JSON reply 提取（不改契约）

候选方案对比：

| 方案 | 契约/prompt | eval 影响 | 风险 |
|---|---|---|---|
| A. 标记协议（`FINAL:` 纯文本答案） | 改模板；与 json mime 冲突，DeepSeek `json_object` 模式不接受纯文本 | 模板是 eval 共用，行为漂移 | 高 |
| **B. 流式输出原 JSON，增量解析提取 reply 字符串**（选定） | 不变 | 零（默认关闭） | 低，新组件可独立单测 |

**核心组件**：新 `harness/streaming.py` 的 `AnswerStreamParser`，状态机三态：

- `DECIDE`：缓冲头部，判定本步输出类型——
  - 出现 `"action":"tool"` → `BUFFER`（工具调用，不流式）
  - 出现 `"reply": "`（字符串值，无论 action 键先后）→ `STREAM`
  - 出现 `"reply":` 后接非 `"`（对象/数字等）→ `BUFFER`（eval 的结构化 answer，整段返回）
  - markdown 围栏 ```json 前缀跳过后再判定
- `STREAM`：增量 JSON 字符串解码（处理 `\"`、`\\`、`\n`、`\uXXXX` 跨 chunk 边界），产出文本 delta
- `BUFFER`：全量累积，不发任何 chunk

**关键性质**：只有确认是字符串 reply 才开始推送；工具调用、格式错误、非字符串 answer 绝不泄漏半个字到前端。与 `_parse_action` 的宽容语义一致（含 reply 键的 dict 按 answer 接受）。

## 3. 接线

1. `ModelAdapter` 协议加可选方法 `complete_stream(prompt) -> AsyncIterator[str | usage 事件]`；`LLMClientAdapter` 用 `LLMClient.chat_stream` 实现（保持 json mime，流式同样输出 JSON）。先确认 chat_stream 的签名与 usage 返回形态，stream 无 usage 时最终步 usage 记 None（total_tokens 只含工具步，done 事件如实反映）。
2. `AgentRunner.run()` 加参数 `stream_answer: bool = False`。为 True 且 adapter 有 `complete_stream` 且传了 `on_event` 时走流式路径：模型输出经 `AnswerStreamParser` 分发，文本 delta 回调 `{"kind": "answer_chunk", "step", "text"}`；完整 raw 仍走现有 `_parse_action`、trace、全量回放逻辑（一字不差）。默认 False，evals 零变化。
3. 流式调用异常 → 回退 `complete()` 非流式（记 trace），不中断 run。
4. 最终 `answer` 事件增加 `streamed_chars` 字段；`server/services/agent_stream.py`：
   - `answer_chunk` → 立即发 `synthesis_chunk {text}`
   - run 结束时若 `streamed_chars < len(answer)`，补发剩余部分（防解析器保守缓冲导致的缺尾）
   - `researcher_done` / `done` 不变

## 4. 测试

- `AnswerStreamParser` 单测：工具调用无 chunk；字符串 answer chunk 拼接 == 解码后 reply；围栏前缀；跨 chunk 的 `\uXXXX` / `\n` 转义；reply 在 action 前；非字符串 reply；非法 JSON 无 chunk；空流。
- Runner 集成：FakeStreamModel 流式输出 answer JSON → on_event 收到有序 answer_chunk 且最终 answer 完整；`stream_answer=False` 时无 chunk（eval 路径保护）；流式中途异常回退 complete()。
- agent_stream 契约：多个 `synthesis_chunk` 依序到达 + 无重复补尾 + total_tokens 正确。
- 回归：全量测试 + eval smoke（DEEPSEEK key 可用）。

## 5. 验收

- `pytest tests/ -q --ignore=tests/test_llm_connectivity.py` 全绿。
- eval smoke 全过（证明 eval 路径零变化）。
- 真实冒烟：curl /api/chat 观察 `synthesis_chunk` 事件多次到达。
- 实验记录追加条目（机制决策：为什么选增量解析而不是标记协议）。

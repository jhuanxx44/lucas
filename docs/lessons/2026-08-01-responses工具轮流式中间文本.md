# DeepSeek Responses 流式：工具轮也会吐 output_text.delta

## 问题

Responses API 迁移后恢复"逐 token 流式"时，工具调用轮的中间叙述被当成最终答案推给前端。模型在调用工具前会先写一段话（如"知识库里没有记录，我联网查一下"），这段文本混进了最终回答。

## 根因

- DeepSeek 工具轮的标准事件顺序是：`output_item.added(reasoning)` → `output_item.added(message)` → `output_text.delta ×N` → `output_item.added(function_call)` → … → `response.completed`。
- message 项和文本 delta 永远先于 function_call 出现，事件顺序不可作为"本轮是否是最终答案"的判定依据；message 项甚至可能被从最终 output 中移除。
- 唯一可靠信号是 `response.completed` 时的最终 turn：`function_calls` 非空 ⇒ 本轮是工具轮，之前流出的文本都不是答案。

## 正确做法

- 适配器（`harness/model_adapter.py`）无条件实时转发 `output_text.delta`；
- runner（`harness/runner.py`）在 turn 完成且确认是工具轮（含被协议纠错拒绝的混合轮）时发出 `answer_discard`；
- SSE 桥转发为 `synthesis_clear`，前端清空已展示的临时文本；
- 不要试图用 item_added 顺序或 message 项判型来"预测"工具轮——真实事件顺序会打脸。

## 验证

- 单测：工具轮流式文本后必有 `answer_discard`；混合轮（function_call + output_text）同样丢弃；
- 真实 API 端到端：多次工具轮后出现 `synthesis_clear`，最终答案无中间叙述，且文本仍逐 token 实时到达。

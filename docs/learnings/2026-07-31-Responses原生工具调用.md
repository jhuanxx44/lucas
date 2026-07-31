# Responses 原生工具调用：让模型负责决策，让代码负责执行

## 这次改造解决了什么

Lucas 旧循环要求模型每轮输出一段自定义 JSON：是调用工具，还是给最终答案，都由
`action/tool/args/reply` 字段表达。Responses API 虽然已经接入，但只被当作“生成 JSON 文本”的
通道，Lucas 还要自行抽取、解析和修正这段文本。

改造后，工具决策直接使用 Responses 的 `function_call` item，工具结果使用
`function_call_output` 回传，任务完成时直接读取 `final_answer` 阶段的文本。模型与 Runner 不再用
一套 Lucas 私有动作语言沟通。

## 一轮工具调用现在怎样流转

```text
Lucas 提交 user input + tools JSON Schema
  → 模型返回 function_call(call_id, name, arguments)
  → Runner 校验调用并执行 ToolRuntime
  → Lucas 追加 function_call_output(call_id, observation)
  → 模型继续调用工具，或返回 final_answer
```

这里最重要的不是字段名，而是职责边界：

- 模型选择工具和生成参数；
- Responses 协议表达调用与结果的关联；
- `ToolRuntime` 仍负责 allowlist、参数 schema、路径边界、权限、超时和实际执行；
- `AgentRunner` 仍负责步数、费用、deadline、重复失败、停滞检测和终止原因。

原生 function calling 不等于把执行权交给 provider。Provider 只能提出调用，真正的副作用始终发生在
Lucas 的受控运行时里。

## 为什么必须保留 call_id

一次工具调用不是只有工具名和参数。Provider 返回的 `call_id` 是这次调用的身份，后续
`function_call_output` 必须带回同一个 ID，模型才能知道结果属于哪次请求。

Lucas 不重新生成 ID，也不把工具结果伪装成普通 user 文本。这样 trace 能准确连接：

```text
function_call_received(call_7)
tool_call_started(call_7)
tool_call_finished(call_7)
function_call_output(call_7)
```

未知、缺失或重复语义错误的 call ID 属于模型协议错误，不应被伪装成一次正常的工具失败。

## 为什么显式保存 Responses items

Responses 支持用 `previous_response_id` 延续服务端会话，但 Lucas 第一阶段没有依赖它。每一轮都显式
提交需要的 input items：初始 user message、上一轮 reasoning/message/function_call items，以及对应的
`function_call_output`。

这个选择会增加请求体大小，却换来三个重要性质：

1. eval 可以复现模型实际看见的上下文；
2. trace 和 artifact 能解释每次决策依据；
3. 将来做 checkpoint 或迁移 provider 时，不依赖一段只存在于远端的隐式状态。

这次真实 PLAN-01 也显示了代价：显式携带完整历史时，长任务 token 增长明显。后续若优化，应通过可测量
的上下文选择或压缩实验解决，而不是先退回隐式会话状态。

## commentary 不是最终答案

DeepSeek 的 Responses 兼容实现会在工具调用旁返回一个 `message`，并标记
`phase=commentary`。SDK 的 `response.output_text` 会聚合这段文字，但它只是“我先查看配置”一类旁白，
不是最终答案。

因此适配器必须按 message phase 归一化：

- `commentary` 单独记录到 trace；
- `final_answer` 才进入 `ModelTurn.output_text`；
- 单个 function call 加 commentary 是合法工具轮；
- function call 加真正的 final answer 仍是冲突决策，需要有界 correction。

用户可见的步骤摘要继续来自工具 schema 中必填的 `summary` 参数，而不是自由文本 commentary。这样
summary 的存在、长度和执行关联仍可由 Lucas 校验。

## `parallel_tool_calls=False` 不是安全边界

真实探针中，即使请求设置了 `parallel_tool_calls=False`，DeepSeek 仍有一次返回两个 function call。
这说明 provider 参数只能作为行为提示，不能替代运行时断言。

Lucas 同时做两层处理：prompt 明确每个 response 最多一个 function call item；Runner 再检查调用数量，
发现多个调用时不执行任何一个，而是进入有界 model correction。串行执行语义因此仍由本地代码保证。

## 最终答案为什么不再套动作 JSON

工具阶段已经有结构化 item，最终阶段只需要用户要看的内容。Runner 直接返回 final answer 文本；如果任务
明确要求 JSON，prompt 要求模型只输出可直接解析的裸 JSON，grader 再按任务契约严格验证。

这与旧 `{"action":"answer","reply":...}` 不同：JSON 是任务本身的结果格式，不是 Agent 循环的控制协议。
普通聊天仍返回普通文本，结构化知识处理则使用 Responses 的 structured output。

## 这次迁移的核心取舍

- 只保留 DeepSeek 官网 Responses 路径，删除多 provider 与 Chat Completions 双栈，降低学习项目的协议噪声。
- Provider-neutral 类型停在 `ModelRequest/ModelTurn/FunctionCall/ModelEvent`，OpenAI SDK 对象不进入 Runner。
- Prompt 负责引导“何时调用、怎样总结”；代码负责所有可执行、可验证的硬语义。
- 不为旧 FakeModel、旧 action JSON 或旧 trace replay 保留兼容层，测试直接使用新的原生类型。

一句话总结：Responses 原生调用减少的是“模型文本与动作之间的翻译层”，没有减少 Lucas 对执行安全、
上下文、可靠性和可观测性的责任。

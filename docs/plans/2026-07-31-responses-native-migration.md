# Lucas 全面迁移 Responses API 计划

## 1. 背景与目标

Lucas 当前虽然已经能通过 DeepSeek 官网调用 Responses API，但仍把它当作文本生成接口使用：模型输出自定义的 `action/tool/args/reply` JSON，`AgentRunner` 解析 JSON 后执行工具，工具结果再以文本 observation 拼回下一轮 prompt。

本次改造采用断代迁移，不保留旧协议兼容层。目标是：

- 只保留 DeepSeek 官网 Responses API；
- 使用 Responses 原生 function calling 表达工具决策；
- 使用 `function_call_output` 回传工具结果；
- 最终答案直接使用 `output_text`，不再套 `action/answer/reply` JSON；
- reasoning、工具调用、最终文本和 usage 使用 Responses 原生事件及数据结构；
- 工具执行、安全、权限、预算、超时、重试和 trace 继续由 Lucas 代码控制；
- 上下文由 Lucas 显式保存，不依赖 provider 服务端隐式会话状态。

不在本次范围内：

- 兼容 Chat Completions、Gemini、MiniMax、Qwen、Claude 或 Beats 旧代理；
- 兼容旧 FakeModel、旧 action JSON、旧 trace replay；
- 使用 `previous_response_id`；
- 使用 provider 内置 Web Search、File Search、Code Interpreter 等托管工具；
- 同一轮并行调用多个工具。

## 2. 机制假设与评估指标

这是一次 Agent Tool/Loop 机制实验，采用 eval-driven 流程。

机制假设：用原生 function calling 取代自定义 action JSON，可以消除动作 JSON 格式错误，降低工具名和参数解析的不确定性，同时保持或提高任务 outcome 成功率和执行稳定性。

主要指标：

- 固定任务 outcome 成功率；
- 工具选择正确率；
- 工具参数 schema 通过率；
- action/format correction 次数，目标为归零；
- 每个任务的模型请求数、工具调用数和总步骤数；
- provider retry、tool retry 和 model correction 次数；
- 首 token 延迟、总延迟；
- 输入、输出和总 token；
- trace 完整性；
- summary 旁白生成率和重复率。

所有对照运行固定模型、temperature、工具、任务 fixture、预算和运行环境。以环境最终状态作为主要验收，transcript 和 trace 仅用于解释原因。

## 3. 目标架构

```text
AgentRunner
    ↓ ModelRequest
ResponsesModelAdapter
    ↓
DeepSeekResponsesClient
    ↓ responses.create(tools=...)
    ↓
ModelTurn
├── function_call
├── output_text
├── reasoning
├── usage
└── response_items
```

职责边界：

- `DeepSeekResponsesClient`：负责 SDK 请求、事件读取、usage 和 provider 错误归一化；
- `ResponsesModelAdapter`：负责 Lucas 类型与 Responses item/tool schema 的双向转换；
- `AgentRunner`：负责循环、决策校验、工具执行、预算、超时、失败恢复和最终结束；
- `ToolRuntime`：负责 allowlist、参数校验、权限、安全边界和 handler 执行；
- SSE 服务：负责把统一 Runner 事件转换成前端事件，不解析 provider 原始对象。

简单 LLM 场景，例如知识库分类、规划和编译，复用同一个 Responses client，但不传入工具。

## 4. 前置能力探针

删除旧实现前，先使用当前 DeepSeek 官网凭据完成最小真实探针，确认以下能力实际可用：

1. 单个 function tool 调用；
2. `strict` JSON Schema；
3. `parallel_tool_calls=False`；
4. `function_call_output` 与 `call_id` 关联；
5. 连续多轮工具调用；
6. 流式 function call 事件；
7. reasoning 与 output text 分离；
8. JSON structured output；
9. usage 字段；
10. 取消、超时和常见 provider 错误的表现。

探针失败时先确认 DeepSeek 的 Responses 兼容范围，不通过 prompt 模拟原生能力。缺少的能力若会阻断 Lucas 核心循环，应停止迁移并记录阻塞原因。

## 5. 固定 baseline

改动生产实现前，对当前 JSON Agent loop 运行 baseline：

- `LOOP-01`；
- `PLAN-01`～`PLAN-04`；
- 产品 SSE 的工具调用、reasoning、summary 和最终答案场景。

每个真实模型任务运行多次 trial，记录成功率、步骤、延迟、token、工具调用、格式修正和 trace。baseline 与改造后使用相同模型、工具、环境和预算。

## 6. 数据协议改造

在 Harness 中定义 provider-neutral 类型，不让 OpenAI SDK 对象进入 Runner：

```python
@dataclass(frozen=True)
class FunctionCall:
    call_id: str
    name: str
    arguments: dict
    summary: str


@dataclass
class ModelTurn:
    output_text: str | None
    function_call: FunctionCall | None
    reasoning: str
    usage: TokenUsage | None
    response_id: str | None
    response_items: list[dict]
```

流式事件至少包含：

```python
ReasoningDelta
OutputTextDelta
FunctionCallCompleted
ResponseCompleted
```

Runner 只消费这些统一类型，不读取 `response.output` 的 SDK 具体类。

## 7. LLM 层重写

将当前多协议 `utils/llm_client.py` 重写为单一 Responses client：

```python
await client.responses.create(
    model=model,
    instructions=instructions,
    input=input_items,
    tools=tools,
    parallel_tool_calls=False,
)
```

配置只保留：

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL
DEEPSEEK_MODEL
```

删除：

- `_GeminiClient`；
- `_OpenAICompatClient`；
- Chat Completions 调用；
- 模型名前缀路由；
- hostname 协议判断；
- `utils/providers.py`；
- `providers.yaml`；
- `OPENAI_*` fallback；
- MiniMax、Qwen、Claude、Gemini 环境变量和文档；
- 不再使用的 Google GenAI 依赖。

Provider transient retry 必须与 model correction、tool retry 分开计数和记录。流式与非流式请求应共享相同的超时、取消和错误归一化策略。

## 8. ToolSpec 与 JSON Schema

当前 `ToolSpec.args_description` 是供 prompt 阅读的字符串，不能直接作为原生 function schema。将其改成真正的 JSON Schema：

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: ToolHandler
```

逐个为现有工具声明 schema，并设定 `additionalProperties: false`。对模型暴露时统一加入必填的 `summary`：

```json
{
  "summary": {
    "type": "string",
    "description": "给用户展示的一句话步骤旁白"
  }
}
```

`summary` 是 Lucas 保留参数名，业务工具不得声明同名参数。Runner 收到 function call 后先提取并剥离 `summary`，再把剩余参数交给 `ToolRuntime`。

API 层设置 `parallel_tool_calls=False`，Runner 仍必须验证单轮至多一个 function call，不能只依赖 provider 行为。

## 9. AgentRunner 循环重写

目标循环：

```text
请求模型
  ├─ 返回 function_call
  │    ├─ 校验 call_id、工具名、参数和 summary
  │    ├─ 发出 summary 事件
  │    ├─ 执行 ToolRuntime
  │    ├─ 追加 function_call_output
  │    └─ 进入下一轮
  │
  └─ 返回 output_text
       └─ 结束任务
```

删除：

- `_parse_action()`；
- `action/tool/args/reply` JSON 解析；
- action JSON 格式修正 prompt；
- 原始 action JSON assistant history；
- 无 action 外壳答案的宽容解析；
- 旧 action format correction 逻辑。

保留并适配：

- allowed tools；
- 参数 schema 和业务校验；
- 重复失败调用检测；
- run deadline；
- model request、tool call、token 和 cost budget；
- tool timeout 与错误结果；
- provider retry、tool retry、model correction 的独立语义；
- trace 和 artifact；
- outcome validation。

无法解析 arguments、缺少 call ID、返回多个工具或工具名不合法时，按有界 model correction 处理，而不是映射成普通工具错误。

## 10. 上下文与工具结果

`StepContext.history` 改为显式 Responses input items，至少保存：

```text
user input
reasoning/function_call response item
function_call_output
下一次 response item
```

工具结果按原生协议回传：

```python
{
    "type": "function_call_output",
    "call_id": call.call_id,
    "output": formatted_observation,
}
```

第一阶段不使用 `previous_response_id`。每次请求由 Lucas 显式提交需要的 input items，以保证 eval 可复现、trace 可解释、checkpoint 可恢复，并避免 provider 隐式状态成为正确性依赖。

## 11. Prompt 精简

`prompts/harness/agent-loop.md` 删除全部 action JSON 格式，改为：

```markdown
---
llm-weight: medium
---

## 工具调用

需要外部信息或执行操作时，调用 API 提供的工具。

- 每轮最多调用一个工具。
- 调用工具时填写 summary，用一句简短口语说明这一步要做什么。
- summary 不复述任务前提、不重复之前内容、不包含工具名等内部术语。
- 调用工具时不要同时输出最终答案。
- 文件路径使用相对工作区根目录的路径。
- 不要重复刚刚失败的相同工具和参数。
- 已获得有效结果后，不要重复相同或高度相似的搜索。

## 最终回答

任务完成后，不再调用工具，直接输出最终答案。

## 任务

{instruction}
```

工具名称、说明和参数从 prompt 中移除，由 Responses `tools` schema 提供。核心 system prompt 只保留全局行为原则，不放输出格式。

“每轮一个工具”、路径安全、重复调用拦截、预算和超时仍由代码保证，prompt 只负责引导模型行为。

## 12. 流式与 SSE

直接消费 Responses 事件：

- reasoning delta → 隐藏 trace；
- function call arguments → 缓冲并在 item 完成后解析；
- output text delta → 最终答案流；
- response completed → usage、response ID 和结束状态。

工具轮不得把模型临时文本泄漏为最终答案。若 provider 允许同一响应同时产生 message 和 function call，Runner 应在 item 类型确定后再决定是否推送文本，并拒绝违反单决策约束的响应。

删除：

- `harness/streaming.py`；
- `AnswerStreamParser`；
- 从 JSON `reply` 中提取字符的状态机；
- action JSON 的流式防泄漏逻辑。

SSE 对外继续保留用户需要的稳定语义：

```text
summary
tool_step
synthesis_chunk
done
error
```

内部 trace 增加：

```text
response_started
reasoning_delta / model_reasoning
function_call_received
function_call_output
response_completed
```

trace 记录 response ID、call ID、模型输入 items、输出 items、usage、延迟和错误分类。

## 13. 配置与上层服务

`lucas.yaml` 删除 `provider` 字段，只保留可选 model 覆盖：

```yaml
single_agent:
  name: Lucas
  model: deepseek-v4-flash
  temperature: 0.0
  max_steps: 0
  allowed_tools: [...]

wiki:
  model: deepseek-v4-flash
```

需要同步修改：

- `harness/config.py`；
- `server/services/agent_stream.py`；
- `server/services/knowledge.py`；
- wiki 构建与评审脚本；
- trace 中的 run config；
- `.env.example` 和 LLM 调用文档。

知识服务继续使用 Responses structured output；AgentRunner 使用原生 function calling 和直接最终文本，二者不要共用 Agent 决策逻辑。

## 14. 测试重写

删除所有依赖旧 action JSON、Chat Completions、Gemini 和 provider 路由的测试，按新协议重写 FakeModel 和断言。

必须覆盖：

- 无工具直接作答；
- 单次工具调用后作答；
- 连续多个工具调用；
- summary 提取和展示；
- 未知或未授权工具；
- arguments 非法 JSON；
- 参数 schema 不合法；
- 缺失或错误 call ID；
- 同一响应返回多个工具；
- 工具调用与最终文本同时出现；
- 工具失败后的模型修正；
- 重复失败调用；
- provider timeout 与 run deadline 分类；
- request、step、token、cost budget；
- reasoning trace；
- 流式最终答案；
- function call 不泄漏到最终答案；
- usage 累计；
- SSE summary/tool/final/error；
- trace 和 artifact 完整性；
- knowledge service structured output。

FakeModel 直接返回 `ModelTurn` 或 `ModelEvent`，不再生成 action JSON 字符串。

## 15. Eval 与实验记录

实现完成后，在相同任务、模型、temperature、工具、环境和预算下对 `LOOP-01`、`PLAN-01`～`PLAN-04` 运行多次 trial。

比较 baseline 与 Responses-native 的：

- outcome 成功率和稳定性；
- 工具选择与参数正确率；
- 步骤和请求数；
- 延迟和 token；
- provider retry、tool retry、model correction；
- summary 质量；
- trace 完整性。

实验报告写入 `docs/experiments/`，运行记录追加到 `docs/experiments/experiment-log.md`。报告必须诚实记录 DeepSeek 原生 Responses 的能力边界和样本量。

这是较大的核心机制改造，完成后另写 `docs/learnings/2026-07-31-Responses原生工具调用.md`，解释原生 function calling、call ID、显式上下文和执行语义的设计取舍。

## 16. 实施顺序

1. 运行能力探针并记录结果；
2. 固定当前 JSON loop baseline；
3. 增加统一 ModelRequest、ModelTurn、FunctionCall 和 ModelEvent；
4. 实现单一 DeepSeek Responses client；
5. 将 ToolSpec 全部改成 JSON Schema；
6. 重写 Runner 原生工具循环和显式 input items；
7. 重写流式、SSE 和 trace；
8. 精简 prompt；
9. 删除旧 LLM、provider、JSON action 和 AnswerStreamParser；
10. 重写单元测试与产品集成测试；
11. 运行相同 eval 多次 trial；
12. 写实验报告、experiment log 和 learning 文档；
13. 清理残留文档、配置、依赖和死代码；
14. 运行全量测试、真实产品冒烟和最终禁止项检查。

每一步先补或更新能证明目标的测试，再实现对应改动。迁移过程中不保留长期双栈；允许短暂的工作区中间状态，但最终提交中只能存在 Responses-native 路径。

## 17. 验收标准

功能验收：

- DeepSeek 官网 Responses 可以完成直接回答、单工具和多工具任务；
- 工具通过原生 function call 调用；
- 工具结果通过 `function_call_output` 回传；
- 最终答案直接来自 `output_text`；
- summary、tool step、reasoning trace 和最终答案事件正确；
- ToolRuntime 的安全、权限、超时和错误语义不退化；
- 固定 eval outcome 成功率不低于 baseline；
- 全量测试通过；
- 真实产品聊天和知识服务冒烟通过。

删除验收：生产代码和当前文档中不再引用：

```text
chat.completions
_GeminiClient
_OpenAICompatClient
providers.yaml
utils.providers
"action": "tool"
"action": "answer"
AnswerStreamParser
OPENAI_BASE_URL
MINIMAX_*
QWEN_*
ANTHROPIC_*
```

历史实验报告和冻结 eval fixture 中的事实记录不做机械篡改；禁止项检查只针对生产实现、当前配置、当前 prompt 和现行文档。

## 18. 主要风险

- DeepSeek Responses 对 function calling 或 strict schema 的兼容范围不足；
- Responses 流式事件与 OpenAI 官方 SDK 类型存在差异；
- 工具 description 从 prompt 迁移到 schema 后，模型选择行为发生漂移；
- 显式携带 response items 导致上下文增长；
- 工具调用与 output text 混合返回导致错误流式展示；
- 旧 action JSON 的宽容解析被删除后，暴露新的 provider 格式边界；
- 大量 FakeModel 和 Runner 测试需要一次性重写，迁移期间主分支可能不可运行。

控制措施：先做真实能力探针和 baseline；按数据协议、工具 schema、Runner、流式四个边界分别增加确定性测试；只在最终全量回归和 eval 完成后提交断代迁移。

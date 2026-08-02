# Lucas LLM 调用指南

Lucas 只支持 **DeepSeek 官网 Responses API**。

## 配置

复制 `.env.example`，至少填写 API Key：

```bash
DEEPSEEK_API_KEY=your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

- `DEEPSEEK_API_KEY`：必填。
- `DEEPSEEK_BASE_URL`：可选，默认 `https://api.deepseek.com`，并且必须指向
  DeepSeek 官网。
- `DEEPSEEK_MODEL`：当调用方和 `lucas.yaml` 都没有指定模型时使用，默认
  `deepseek-v4-flash`。

产品 Agent 和 wiki 服务使用的模型在 `lucas.yaml` 中显式配置。代码中的显式
`model` 参数优先级最高。

## 普通文本调用

知识分类、规划、编译等不需要工具循环的场景使用 `generate_text`：

```python
from utils.llm_client import create_client

client = create_client(model="deepseek-v4-flash")
text, usage = await client.generate_text(
    "用一句话解释市盈率。",
    instructions="你是一个严谨的投研助手。",
    temperature=0,
)
```

需要 JSON 对象时声明响应类型：

```python
text, usage = await client.generate_text(
    "返回一个包含 ok 字段的 JSON 对象。",
    response_mime_type="application/json",
)
```

`usage` 是统一的 `TokenUsage`，包含输入、普通输出、reasoning、总 token 和延迟。

## 原生 Responses 调用

底层能力可以通过 `create` 直接使用：

```python
response = await client.create(
    input="Hi, how are you?",
    instructions="You are a helpful assistant.",
)
print(response.output_text)
```

`create` 支持 `input`、`instructions`、`tools`、`temperature`、`text`、
`stream`、`max_output_tokens` 和 `parallel_tool_calls`。传入工具时，调用层
默认设置：

```text
tool_choice = auto
parallel_tool_calls = true
```

`parallel_tool_calls` 允许模型单轮返回多个互不依赖的 `function_call`（并行
工具调用）；Runner 对单轮并行数量设上限（`MAX_PARALLEL_TOOL_CALLS`，默认 4），
超出按协议错误纠正。并行轮中每个 `function_call` 都必须返回对应的
`function_call_output`（带各自 `call_id`）；同一批调用由 Runner 并发执行
（先广播整批 `tool_start`，结果按原顺序回传），全部执行完再进入下一轮。

## Agent 工具循环

Agent 不再要求模型输出 `action/tool/args/reply` JSON。工具通过 Responses 的
function tools schema 下发，模型返回 `function_call`，Lucas 执行后以带
`call_id` 的 `function_call_output` 回传。任务完成时，最终回答直接取
`output_text`。

职责分工：

- `utils/llm_client.py`：请求、流式传输、重试和 usage；
- `harness/model_adapter.py`：工具 schema、Responses item 与 Lucas 类型转换；
- `harness/runner.py`：工具执行、权限、预算、超时、上下文和 trace。

上下文由 Lucas 显式保存，不使用 `previous_response_id`。这样 eval、trace、恢复
和 provider 请求输入都可复现。

## 流式事件

Agent adapter 只消费并归一化需要的 Responses 事件：

- reasoning delta → 推理 trace；
- output text delta → 最终答案流；
- completed → 完整 `ModelTurn`、response id 和 usage。

function call 参数在完成后统一校验，工具调用内容不会混入最终答案文本。

## 错误与重试

调用层只对限流、服务端错误和连接重置等短暂故障做有限重试。工具参数错误、
非法工具名和循环无进展属于 Agent 层校正，不计入 provider retry。API Key 缺失
或 endpoint 不是 `api.deepseek.com` 时会立即报错。

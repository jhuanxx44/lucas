# LLM 客户端支持 tool_calls 解析

## 这是什么

给 Lucas 的 LLM 调用层加上了"听懂模型说'我想调工具'"的能力。之前模型只能回文字，现在它能回"帮我读这个文件"或"帮我跑个命令"，我们的代码再把这句话翻译成实际执行。

## 要解决什么问题

LLM 不会真的操作你的电脑，它只能输出文字。要让 Agent 干活，需要一种约定：模型说"我想调这个工具，参数是这些"，代码收到了就去执行，把结果再告诉模型，如此循环。

OpenAI 定义了一套标准格式来表示这个意图，叫 tool_calls。当模型决定调工具时，返回的不是普通文本，而是一个结构化的 JSON：

```json
{
  "tool_calls": [{
    "function": {
      "name": "read_file",
      "arguments": "{\"path\": \"/tmp/data.txt\"}"
    }
  }]
}
```

Lucas 之前只处理了普通文本回复，遇到 tool_calls 就直接忽略了。这导致 Agent 无法自动调用工具——相当于机器人只能说不能做。

## 核心设计

### 1. 多 provider 兼容

不同厂商返回 tool_calls 的格式略有差异，有的用 `tool_calls`，有的用 `function_call`，有的是 dict 有的是对象。核心逻辑用三层兜底来兼容：

```
tool_calls = getattr(msg, "tool_calls", None) or getattr(msg, "function_call", None)
```

先找标准名 `tool_calls`，找不到再用 `function_call`（旧版 OpenAI / Claude 的字段名）。

### 2. 统一输出格式

不管调用方是谁，最终都序列化成同一个结构：

```json
{"action": "tool", "tool": "<工具名>", "args": {<参数>}}
```

这样下游代码（比如 Harness 里的 AgentRunner）就不用关心具体是 DeepSeek、MiniMax 还是 Claude，只管解析这个统一格式。

### 3. 参数自动反序列化

arguments 有时候是 JSON 字符串（需要 `json.loads`），有时候已经是 dict。统一处理：

```python
if isinstance(args, str):
    args = json.loads(args)
```

## 取舍

- **只取第一个 tool call**：当前不处理并行调用。Lucas 阶段走的是串行工具循环，一次一个工具足够覆盖需求，并行调用复杂度高且收益不明确。
- **不会报错**：如果模型没返回 tool_calls，直接走原来的文本回复逻辑，向后完全兼容。
- **不拦截无效工具**：这里只管解析格式，不验证工具名是否合法。合法性由调用方（AgentRunner）的 ToolRuntime 来校验。

## 一句话总结

LLM 返回的不是文字就是工具调用——之前只能读懂前者，现在两个都能接住，而且不管背后是 DeepSeek、MiniMax 还是 Claude，外面的代码看到的格式都一样。

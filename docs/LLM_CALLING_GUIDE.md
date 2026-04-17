# LLM 调用指南（最小可复用版）

> 本项目通过 Google GenAI SDK 调用 LLM，但**不直连 Google**，而是走内部代理（Beats）。
> 核心思路：用 `vertexai=True` 的协议格式 + 自定义 `base_url` 指向代理。

---

## 1. 环境变量

```bash
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=http://llmapi.bilibili.co/v1   # 内部代理地址
OPENAI_MODEL=gemini-3.1-pro                     # 默认模型
```

> 变量名叫 `OPENAI_*` 是历史原因，实际走的是 Gemini 协议。

---

## 2. 核心客户端（`utils/llm.py`）

### 初始化

```python
from google import genai
from google.genai import types

client = genai.Client(
    api_key=api_key,
    vertexai=True,                    # 仅表示用 Vertex AI 协议格式
    http_options={
        "base_url": f"{base_url}/gemini/",  # 实际请求地址，拼接 /gemini/
        "timeout": 1200000,
    },
)
```

关键点：
- `vertexai=True` **不等于直连 Google**，只是协议格式
- 实际请求地址由 `base_url` 决定（指向内部代理）

### 非流式调用

```python
from utils.llm import GeminiClient

client = GeminiClient(
    model="gemini-3.1-pro",
    system_prompt="你是一个助手",     # 可选
    enable_thinking=True,             # 默认开启 thinking 模式
)

text, token_usage = await client.chat(
    prompt="你的问题",
    images=["https://example.com/img.jpg"],   # 可选，支持 URL 和本地路径
    videos=["local_video.mp4"],               # 可选
    response_mime_type="application/json",     # text/plain 或 application/json
    temperature=0.7,                           # 可选，默认 1.0
    thinking_budget=24576,                     # 可选，默认 24576
)
```

返回值：`(str, Optional[TokenUsage])`

### 流式调用

```python
async for chunk in client.chat_stream(
    prompt="你的问题",
    response_mime_type="text/plain",
):
    print(chunk, end="", flush=True)
```

### 便捷工厂函数

```python
from utils.llm import create_client

client = create_client(model="gemini-3.1-pro", system_prompt="...")
```

---

## 3. System Prompt 实现方式

SDK 不直接支持 system role，项目用 **user/model 对话模拟**：

```python
contents = [
    Content(role="user",  parts=[Part(text=system_prompt)]),
    Content(role="model", parts=[Part(text="好的，我明白了。")]),
    Content(role="user",  parts=[Part(text=user_prompt)]),
]
```

---

## 4. 重试机制

内置自动重试，无需调用方处理：

- 可重试错误：`429`（限流）、`499`（代理断连）、`500/502/503/504`
- 空响应也会重试
- 固定退避：3s → 5s → 10s，最多 3 次

---

## 5. 多模型路由（Motion Service）

`motion_service/core/llm_caller.py` 根据模型名前缀自动选择客户端：

| 前缀 | 客户端 | 说明 |
|------|--------|------|
| `gemini-*` | `GeminiClient` | Google GenAI SDK |
| `glm-*` / `ppio/*` / `huawei/*` / `zai/*` / `MiniMax-*` | `ZhipuClient` | OpenAI SDK 兼容 |
| `deepseek-*` | `DeepSeekClient` | OpenAI SDK 兼容 |

三个客户端接口统一：`await client.chat(prompt, ...) → (str, TokenUsage)`

---

## 6. 多模态输入

`GeminiClient` 支持图片和视频，自动处理 URL 下载和本地文件读取：

```python
text, _ = await client.chat(
    prompt="描述这张图片",
    images=[
        "https://example.com/photo.jpg",       # URL
        "/local/path/image.png",               # 本地路径
        {"path": "img.jpg", "alias": "封面"},   # dict 格式，带别名
    ],
    videos=["https://example.com/video.mp4"],
)
```

---

## 7. Token 统计

每次调用返回 `TokenUsage` 对象：

```python
text, token_usage = await client.chat(prompt="...")
if token_usage:
    print(f"输入: {token_usage.prompt_tokens}")
    print(f"输出: {token_usage.completion_tokens}")
    print(f"思考: {token_usage.thinking_tokens}")
    print(f"耗时: {token_usage.latency_ms}ms")
    print(f"费用: ${token_usage.total_cost:.4f}")
```

---

## 8. 最小可运行示例

```python
import asyncio
from utils.llm import GeminiClient

async def main():
    client = GeminiClient(model="gemini-3.1-pro")

    # 纯文本
    text, usage = await client.chat(prompt="用一句话介绍 Python")
    print(text)

    # 要求 JSON 输出
    json_text, _ = await client.chat(
        prompt="列出 3 种编程语言，返回 JSON 数组",
        response_mime_type="application/json",
    )
    print(json_text)

asyncio.run(main())
```

---

## 9. 架构总结

```
调用方代码
    │
    ▼
GeminiClient / ZhipuClient / DeepSeekClient   ← 统一接口
    │
    ▼
Google GenAI SDK (vertexai=True)  /  OpenAI SDK
    │
    ▼
内部代理 (Beats: llmapi.bilibili.co)          ← base_url 控制
    │
    ▼
实际 LLM 服务 (Gemini / GLM / DeepSeek / ...)
```

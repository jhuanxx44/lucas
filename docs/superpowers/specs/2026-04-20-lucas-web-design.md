---
title: Lucas Web 应用设计规格
date: 2026-04-20
status: draft
---

# Lucas Web 应用设计规格

## 1. 概述

将 Lucas A股智能分析系统从 CLI 升级为 Web 应用。保留现有 agents/ 多 Agent 架构，新增 FastAPI 后端 + React 前端，提供 Wiki 知识库浏览和对话式分析两大功能。

**核心决策：**
- 架构：Monorepo 单体，FastAPI serve React 静态文件
- 数据存储：继续用文件系统，wiki/ 目录下的 Markdown 文件就是数据源
- 对话通信：SSE 流式，支持多研究员并行可视化
- 前端：Vite + React + shadcn/ui + Tailwind
- 用户范围：先个人使用，架构上留扩展空间

## 2. 页面布局

单页三栏布局，不做路由切换：

```
+----------------------------------------------------------+
|  Lucas    A股智能分析系统              🔍 搜索/提问...     |
+----------+------------------------+----------------------+
| Wiki 目录 |     Wiki 内容          |     对话分析          |
| (可折叠)  |   (Markdown 渲染)      |  (聊天 + 研究员卡片)  |
|           |                        |                      |
| 📂 公司   |  宁德时代（300750）     |  🧑 研究下东山精密     |
|  ├ 宁德   |                        |                      |
|  ├ 胜宏   |  动力电池全球龙头...    |  📊 基本面 ✓ 完成     |
|  └ 沪电   |                        |  📈 技术面 ⏳ 分析中   |
|           |  ## 概述               |                      |
| 📂 行业   |  ...                   |  🧠 综合分析          |
|  └ PCB    |                        |  等待研究员完成...     |
|           |  ## 相关链接           |                      |
| 📂 概念   |  [[PCB]] [[AI算力]]    | +--------------------+|
|  └ AI算力 |                        | | 输入问题...   [发送]||
|           |                        | +--------------------+|
+----------+------------------------+----------------------+
```

**三栏宽度可拖拽调整。**

**Wiki-对话联动：**
- 默认联动模式：对话中分析某公司时，Wiki 区自动跳转到该公司页面
- 联动方向：对话 → Wiki（单向），对话触发 Wiki 跳转，但手动浏览 Wiki 不影响对话
- 顶栏提供联动开关，可切换为独立模式（Wiki 和对话互不干扰）

## 3. 后端 API

### 3.1 Wiki 浏览 (REST)

**`GET /api/wiki/index`**
- 解析 wiki/index.md，返回结构化目录树
- 响应格式：
```json
{
  "sections": [
    {
      "title": "公司档案",
      "items": [
        {"name": "宁德时代", "path": "companies/300750-宁德时代.md"}
      ]
    }
  ]
}
```

**`GET /api/wiki/{path:path}`**
- 读取 wiki/ 下指定 Markdown 文件
- 解析 YAML frontmatter 和正文
- 响应格式：
```json
{
  "frontmatter": {
    "title": "宁德时代",
    "type": "company",
    "tags": ["动力电池", "储能"],
    "confidence": "high",
    "updated": "2026-04-17",
    "sources": ["raw/financial-reports/..."]
  },
  "content": "Markdown 正文...",
  "wiki_links": ["PCB", "AI算力"]
}
```

**`GET /api/wiki/search?q=关键词`**
- 基于文件系统的简单搜索：匹配文件名 + 内容关键词
- 返回匹配的页面列表（路径、标题、匹配片段）
- 不引入搜索引擎，grep 式实现

### 3.2 对话分析 (SSE)

**`POST /api/chat`**
- 请求体：`{"question": "研究下东山精密", "history": [...]}`
- 返回 SSE 流（`text/event-stream`）
- history 为前端维护的对话历史数组，每项 `{"role": "user"|"assistant", "content": "..."}`

SSE 事件类型：

| event | data 字段 | 说明 |
|-------|----------|------|
| `status` | `{"message": "正在分析意图..."}` | 状态更新 |
| `dispatch` | `{"action": "research", "researchers": ["fundamental", "technical"]}` | 意图识别结果 |
| `researcher_start` | `{"id": "fundamental", "name": "基本面分析"}` | 研究员开始工作 |
| `researcher_chunk` | `{"id": "fundamental", "text": "东山精密是..."}` | 研究员流式文本片段 |
| `researcher_done` | `{"id": "fundamental", "tokens": 1234}` | 研究员完成 |
| `synthesis_chunk` | `{"text": "综合来看..."}` | 综合分析流式输出 |
| `done` | `{"total_tokens": 5678, "report_path": "wiki/reports/..."}` | 全部完成 |
| `error` | `{"message": "分析出错: ..."}` | 错误 |

对于 `action: "direct"` 的情况（闲聊、简单查询），直接通过 `synthesis_chunk` 流式返回 Manager 的回复，不经过研究员。

## 4. 后端改造

### 4.1 LLM Client 流式支持

在 `utils/llm_client.py` 的 `LLMClient` 基类新增：

```python
@abc.abstractmethod
async def chat_stream(
    self,
    prompt: str,
    temperature: Optional[float] = None,
    thinking_budget: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """流式返回文本片段"""
    ...
```

`_GeminiClient` 和 `_OpenAICompatClient` 各自实现流式版本。

### 4.2 Manager 流式化

将 `Manager.analyze()` 改造为 async generator：

```python
async def analyze_stream(
    self, question: str, history: list[dict] = None
) -> AsyncGenerator[dict, None]:
    """流式分析，yield SSE 事件 dict"""
    yield {"event": "status", "data": {"message": "正在分析意图..."}}

    dispatch = await self._dispatch(question, history)
    yield {"event": "dispatch", "data": dispatch}

    if dispatch["action"] == "direct":
        async for chunk in self._direct_reply_stream(question, history):
            yield {"event": "synthesis_chunk", "data": {"text": chunk}}
    elif dispatch["action"] == "research":
        async for event in self._research_stream(question, dispatch, history):
            yield event

    yield {"event": "done", "data": {"total_tokens": self._token_count}}
```

保留现有 `analyze()` 方法不变，CLI 继续用它。

### 4.3 研究员并行流式

多个研究员并行时，用 `asyncio.TaskGroup` 并发执行，每个研究员的 chunk 通过 `asyncio.Queue` 汇聚到主 generator：

```python
async def _research_stream(self, question, dispatch, history):
    queue = asyncio.Queue()

    async def run_one(researcher_id):
        yield {"event": "researcher_start", ...}
        async for chunk in researcher.analyze_stream(...):
            await queue.put({"event": "researcher_chunk", "data": {"id": researcher_id, "text": chunk}})
        await queue.put({"event": "researcher_done", ...})

    async with asyncio.TaskGroup() as tg:
        for rid in dispatch["researchers"]:
            tg.create_task(run_one(rid))
        # 同时从 queue 读取事件 yield 出去
```

## 5. 前端架构

### 5.1 技术栈

- Vite + React 18 + TypeScript
- shadcn/ui + Tailwind CSS
- react-markdown（wiki 渲染）
- 无路由库（单页三栏，不需要）
- 无全局状态库（useReducer + Context 够用）

### 5.2 组件结构

```
web/src/
  App.tsx                  ← 三栏布局容器
  components/
    TopBar.tsx             ← 顶栏：logo、搜索、联动开关
    WikiSidebar.tsx        ← 左侧目录树
    WikiContent.tsx        ← 中间 wiki Markdown 渲染
    ChatPanel.tsx          ← 右侧对话区容器
    ChatInput.tsx          ← 输入框 + 发送按钮
    ChatMessage.tsx        ← 单条消息（用户/系统）
    ResearcherCard.tsx     ← 研究员卡片（状态 + 流式文本）
    SynthesisCard.tsx      ← 综合分析卡片
    ResizableDivider.tsx   ← 可拖拽分隔线
  hooks/
    useSSE.ts              ← SSE 连接管理 + 事件分发
    useWikiNavigation.ts   ← Wiki 联动 context
    useChat.ts             ← 对话状态 reducer
  lib/
    api.ts                 ← fetch 封装（wiki REST API）
    markdown.ts            ← Markdown 处理（[[wiki链接]] 解析等）
  types/
    index.ts               ← 共享类型定义
```

### 5.3 关键 Hook

**`useSSE`** — 管理 SSE 连接：
- 发送 POST fetch 请求到 `/api/chat`，通过 ReadableStream 读取 SSE 响应（不用 EventSource，因为 EventSource 只支持 GET）
- 解析 `event:` / `data:` 行，按 event type 分发到对应 handler
- 处理超时、错误、abort（用户发新问题时取消上一个请求）

**`useChat`** — 对话状态 reducer：
```typescript
type ChatState = {
  messages: Message[]           // 对话历史
  researchers: Map<string, ResearcherState>  // 研究员状态
  synthesis: string             // 综合分析文本
  isLoading: boolean
}

type Action =
  | { type: 'USER_MESSAGE'; question: string }
  | { type: 'RESEARCHER_START'; id: string; name: string }
  | { type: 'RESEARCHER_CHUNK'; id: string; text: string }
  | { type: 'RESEARCHER_DONE'; id: string }
  | { type: 'SYNTHESIS_CHUNK'; text: string }
  | { type: 'DONE'; tokens: number }
```

**`useWikiNavigation`** — Wiki 联动 context：
- 提供 `navigateTo(path)` 方法
- 对话区收到 `dispatch` 事件时，解析涉及的公司/概念，调用 `navigateTo`
- 联动开关关闭时，`navigateTo` 变为 no-op

### 5.4 Wiki 链接处理

wiki 页面中的 `[[双括号链接]]` 在 Markdown 渲染前预处理：
- 解析 `[[页面名]]` → 查找对应的 wiki 路径
- 渲染为可点击的链接，点击时更新 Wiki 区内容

## 6. 项目文件结构

```
lucas/
  agents/              ← 现有，不动
  utils/               ← 现有，新增 chat_stream 方法
  prompts/             ← 现有，不动
  raw/                 ← 现有，不动
  wiki/                ← 现有，不动
  server/
    __init__.py
    app.py             ← FastAPI 入口
    routers/
      __init__.py
      wiki.py          ← wiki REST API
      chat.py          ← 对话 SSE endpoint
    services/
      __init__.py
      stream.py        ← Manager 流式包装
  web/
    package.json
    vite.config.ts
    tsconfig.json
    tailwind.config.ts
    index.html
    src/
      main.tsx
      App.tsx
      components/      ← 见 5.2
      hooks/           ← 见 5.3
      lib/
      types/
  cli.py               ← 现有 CLI，保留不动
  agents.yaml           ← 现有，不动
  providers.yaml        ← 现有，不动
```

## 7. 开发和部署

**开发模式：**
- 后端：`python -m server.app`（FastAPI + uvicorn，端口 8000）
- 前端：`cd web && npm run dev`（Vite dev server，端口 5173，proxy 到 8000）
- vite.config.ts 配置 proxy，开发时前端请求自动转发到后端

**生产模式：**
- `cd web && npm run build` → 输出到 `web/dist/`
- FastAPI mount `web/dist/` 为静态文件
- 单命令启动：`python -m server.app`，单端口 serve 全部内容

## 8. 不做的事情

- 不引入数据库 — 文件系统就是数据源
- 不做用户认证 — 先个人使用
- 不做对话持久化 — 分析结果已归档到 wiki/reports/，对话历史刷新即清
- 不做 WebSocket — SSE 单向流式够用
- 不引入全局状态库 — useReducer + Context 够用
- 不做移动端适配 — 三栏布局面向桌面
- 不改现有 CLI — 保留 cli.py 原样可用

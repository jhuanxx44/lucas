# Vercel 部署分析

## 项目结构

| 层 | 技术栈 | 部署方式 |
|---|--------|----------|
| 前端 (`web/`) | Vite + React + TypeScript | 静态站点，**适合 Vercel** |
| 后端 (`server/`) | FastAPI + uvicorn | ASGI 服务，**不适合 Vercel Serverless** |

## 前端：适合 Vercel

Vite 构建产物是纯静态文件（`web/dist/`），Vercel 原生支持，预览部署开箱即用。

需要调整：
- API 地址硬编码为相对路径 `/api`，需改为 `VITE_API_BASE_URL` 环境变量
- Vercel 上 `/api` 请求需要指向已部署的后端地址

## 后端：不适合 Vercel Serverless

| 问题 | 说明 |
|------|------|
| **本地文件系统写入** | 核心逻辑依赖 `workspaces/{user_id}/wiki/`、`raw/`、`memory/` 目录读写。Vercel Serverless 文件系统是临时的，冷启动数据全部丢失 |
| **重型依赖** | `akshare`（A股数据）、`openai`、`google-genai` 等包体积大，容易超过 Vercel 250MB 部署限制 |
| **超时限制** | LLM 调用 + SSE 流式响应需要 30-120 秒。Vercel Hobby 限制 10s，Pro 最大 300s |
| **SSE 长连接** | chat 和 ingest 端点使用 `StreamingResponse`（text/event-stream），Serverless 函数超时即截断 |

架构层面上，这是一个**有状态的文件系统驱动应用**，Vercel Serverless 的无状态模型从根本上不匹配。要迁就至少需要：引入对象存储替代文件系统、拆分流式端点到独立长连接服务、精简依赖包体积——相当于重写整个后端的数据层。

## 后端部署方案

本项目的部署模型是单进程：`npm run build`（构建前端） + `python -m server.app`（FastAPI 同时 serve 前端和 API）。以下平台开箱即用，无需写 Dockerfile 或复杂配置。

### Fly.io（推荐）

```bash
fly launch   # 自动探测 FastAPI 项目，生成 fly.toml
fly deploy   # 每次更新
```

- 全程 CLI 操作，不需要开网页控制台
- 自动检测 Python/Node 项目并生成配置
- 免费额度：3 个共享 CPU + 256MB 内存 + 3GB 持久卷（wiki 数据持久化）
- 加一个持久卷挂在 `workspaces/` 目录即可解决文件系统写入问题

### Railway

- 连 GitHub 仓库，自动检测自动部署
- 初始关联需要一次网页操作，之后零配置
- 免费额度起步

### 部署策略

两种思路，看需求选择：

**单进程部署**（最简单）：
在 Fly.io 上跑 `python -m server.app`，FastAPI 自己 serve `web/dist/` 前端静态文件。一个进程搞定全部，和本地 `dev.sh` 的体验一致。

**前后端分离**：
前端放 Vercel（预览部署），后端放 Fly.io。前端通过 `VITE_API_BASE_URL` 指向后端地址。好处是前端每次 PR 自动预览，但要处理 CORS。

## 结论

- **前端可以用 Vercel 部署**，简单且预览部署功能可用
- **后端不适合 Vercel Serverless**，推荐 **Fly.io**（CLI 驱动，最省事）或 **Railway**（Git 驱动）
- 单进程部署最简单，localhost 怎么跑线上就怎么跑

# Lucas — 投研认知的复利引擎

基于 Karpathy LLM Wiki 模式构建的A股专属知识库，持续将原始资料编译为结构化认知，配合多 Agent 专家系统进行深度分析。

## 结构

```
raw/          原始资料（只读）
wiki/         LLM编译的结构化Wiki
prompts/      编译模板
agents/       多Agent专家系统
agents.yaml   研究员配置
providers.yaml 模型提供商配置
server/       FastAPI 后端
web/          React 前端
utils/        LLM统一调用层
```

## 快速启动

```bash
./dev.sh
```

一键启动前后端。后端 `localhost:8000`，前端 `localhost:5173`，`Ctrl+C` 同时关闭。

生产部署：先 `cd web && npm run build`，再 `python -m server.app`——FastAPI 会自动 serve 静态文件。

## 可用模型

配置见 `providers.yaml`，当前支持：

| Provider | 默认模型 | 路由 |
|----------|----------|------|
| MiniMax | `MiniMax-M2.7` | OpenAI 兼容 |
| Gemini | `gemini-3.1-pro` | OpenAI 兼容 |
| DeepSeek | `deepseek-v3` | OpenAI 兼容 |
| Qwen | `qwen-plus` | OpenAI 兼容 |
| Claude | `claude-3-5-sonnet` | OpenAI 兼容 |

## 使用方式

### Wiki 编译
1. 将原始资料放入 `raw/` 对应子目录
2. 让 LLM 编译：`"编译 raw/research/xxx.md"`
3. LLM 自动生成/更新 wiki 页面并维护索引

### Agent 分析
1. 启动 `./dev.sh`，打开浏览器访问前端
2. 输入问题（如"分析宁德时代"）
3. Lucas 自动派发给相关研究员，汇总多视角分析

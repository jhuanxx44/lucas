# Lucas — 投研认知的复利引擎

基于 Karpathy LLM Wiki 模式构建的A股专属知识库，持续将原始资料编译为结构化认知，配合多 Agent 专家系统进行深度分析。

## 结构

```
raw/          原始资料（只读）
wiki/         LLM编译的结构化Wiki
prompts/      编译模板
reviews/      多LLM交叉验证记录
logs/         编译日志
agents/       多Agent专家系统
agents.yaml   研究员配置
utils/        LLM统一调用层
```

## 快速启动

### CLI 模式

```bash
./cli.sh
```

进入交互式 CLI，输入问题即可。Lucas 会自动分析意图、选择研究员、汇总结果。

### Web 模式

```bash
./dev.sh
```

一键启动前后端。后端 `localhost:8000`，前端 `localhost:5173`，`Ctrl+C` 同时关闭。

生产部署：先 `cd web && npm run build`，再 `python -m server.app`——FastAPI 会自动 serve 静态文件。

## 可用模型（内部代理）

| 模型 | 路由 | 状态 |
|------|------|------|
| `gemini-3.1-pro` | Gemini SDK | ✅ |
| `deepseek-v3.2` | OpenAI 兼容 | ✅ |
| `claude-4.6-opus` | OpenAI 兼容 | ✅ |
| `glm-5-turbo` | OpenAI 兼容 | ✅ |
| `qwen3.5-plus` | OpenAI 兼容 | ✅ |

## 使用方式

### Wiki 编译
1. 将原始资料放入 `raw/` 对应子目录
2. 让 LLM 编译：`"编译 raw/research/xxx.md"`
3. LLM 自动生成/更新 wiki 页面并维护索引

### Agent 分析
1. 运行 `./cli.sh` 启动 CLI
2. 输入问题（如"分析宁德时代"）
3. Lucas 自动派发给相关研究员，汇总多视角分析

详见 [CLAUDE.md](CLAUDE.md) 和 [AGENTS.md](AGENTS.md)。

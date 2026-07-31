# Lucas — 投研认知的复利引擎

基于 Karpathy LLM Wiki 模式构建的A股专属知识库，持续将原始资料编译为结构化认知，配合单 Agent（ReAct 循环）进行深度分析。

当前按本地单用户模式运行，数据直接存放在项目根目录的 `raw/`、`ingested/`、`reports/`、`wiki/` 和 `memory/`。

## 结构

```
raw/          原始资料（只读）
ingested/     系统抓取或通过界面收录的资料
reports/      Agent 生成的报告、元数据和证据 sidecar
wiki/         LLM编译的结构化Wiki
prompts/      编译模板
harness/      通用 AgentRunner（single 模式 ReAct 循环）与工具集
lucas.yaml    Agent 与 wiki 领域配置
server/       FastAPI 后端（services/agent_stream.py 聊天链路、services/knowledge.py wiki 收录编译）
web/          React 前端
utils/        DeepSeek Responses API 调用层
```

## 快速启动

```bash
./dev.sh
```

一键启动前后端。后端 `localhost:8000`，前端 `localhost:5173`，`Ctrl+C` 同时关闭。

生产部署：先 `cd web && npm run build`，再 `python -m server.app`——FastAPI 会自动 serve 静态文件。

## LLM 配置

Lucas 只使用 DeepSeek 官网 Responses API。复制 `.env.example` 并填写
`DEEPSEEK_API_KEY`；endpoint 默认为 `https://api.deepseek.com`，模型由
`lucas.yaml` 显式配置，也可用 `DEEPSEEK_MODEL` 作为缺省值。

调用约定和示例见 [`docs/LLM_CALLING_GUIDE.md`](docs/LLM_CALLING_GUIDE.md)。

## 使用方式

### Wiki 编译
1. 将原始资料放入 `raw/` 对应子目录
2. 让 LLM 编译：`"编译 raw/research/xxx.md"`
3. LLM 自动生成/更新 wiki 页面并维护索引

`raw/` 是不可变输入；Lucas 不会向其中写入。通过界面或 URL 收录的资料进入 `ingested/`，Agent 分析产物进入 `reports/`。

### Agent 分析
1. 启动 `./dev.sh`，打开浏览器访问前端
2. 输入问题（如"分析宁德时代"）
3. Lucas 由单个 Agent 自主调用行情、搜索和 wiki 召回工具完成分析

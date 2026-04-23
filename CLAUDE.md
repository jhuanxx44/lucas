# Lucas

A股股市 LLM Wiki — 基于 Karpathy LLM Wiki 模式，多 Agent 协作分析A股市场。

你是 Agent 设计专家兼资深全栈开发。从第一性原理出发，目标或路径不清晰时先讨论再动手。用中文回复。

## 命令

```bash
./dev.sh                    # 一键启动前后端（后端 :8000，前端 :5173）
pytest                      # 跑全部测试
pytest tests/test_xxx.py    # 跑单个测试
cd web && npm run build     # 构建前端（产物 web/dist/，后端自动 serve）
cd web && npm run dev       # 单独启动前端 dev server
```

## 技术栈

- 后端：FastAPI + uvicorn（`server/`），API 前缀 `/api`
- 前端：React 19 + Vite + Tailwind（`web/`）
- Agent 系统：Python，Manager-Researcher 架构（`agents/`）
- LLM 调用：统一走 OpenAI SDK 兼容接口，支持多 provider
- 数据源：akshare（A股行情）、tavily/ddgs（搜索）

## 架构

```
server/          FastAPI 后端
  routers/       chat.py（SSE 聊天）、wiki.py（wiki API）
  services/      stream.py（流式输出）、wiki_parser.py
agents/          多 Agent 系统
  manager.py     Manager：派发子任务、聚合结论
  researcher.py  Researcher：执行具体分析
  config.py      从 agents.yaml 加载配置
  models.py      数据模型
  tools.py       工具调用（行情、搜索）
web/             React 前端
prompts/         LLM prompt 模板（dispatch、synthesis 等）
raw/             原始资料（只读，不要修改）
wiki/            LLM 编译输出的 wiki 页面
utils/           provider 管理、通用工具
```

## 配置

- `agents.yaml` — Agent 角色定义（manager + researchers），每个 agent 指定 provider 和 system_prompt
- `providers.yaml` — LLM provider 配置（gemini/minimax/deepseek/qwen/claude），映射 env var 名
- `.env` — API keys（参考 `.env.example`），按需配置使用的 provider

## 关键约束

- `raw/` 目录只读，永远不要修改或删除其中的文件
- wiki 内容用中文撰写，区分事实和观点，观点标注来源
- Agent 系统的 prompt 模板在 `prompts/` 目录，修改 agent 行为优先改 prompt 而非硬编码
- 前后端开发时 CORS 已配置 localhost:5173 和 localhost:8000

## LLM 调用分级

每个 prompt 模板和内联 LLM 调用都用 `llm-weight` 标注复杂度，为未来模型分流做准备。

- `heavy` — 深度推理、长文生成、核心产出。当前用主力模型。
  - researcher 分析（agents.yaml 定义）、synthesis、wiki-compile、raw-compile、tool-use
- `medium` — 结构化判断、分类决策。当前用主力模型，未来可降级。
  - dispatch、wiki-plan、raw-classify
- `light` — 短文本提取、JSON 抽取。当前用主力模型，未来应换小模型以提速降本。
  - title-extract、conclusion-extract、preference-extract、stock_data._extract_company_names

新增 LLM 调用时必须在 prompt 文件 frontmatter 或 docstring 中标注 `llm-weight`。

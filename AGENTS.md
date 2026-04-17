# Lucas — 多 LLM 协作规范

本文件定义了多个 LLM（Claude、GPT、Gemini 等）在本知识库中的协作规则。

## 共享约定

所有 LLM 遵守相同的目录和格式规范：

- `raw/` 只读，任何 LLM 都不得修改
- `wiki/` 页面格式遵循 CLAUDE.md 中定义的 frontmatter 规范
- `prompts/` 中的编译模板对所有 LLM 通用
- `reviews/` 用于记录交叉验证结果

## 角色分工

每个 LLM 在参与时需声明自己的角色：

| 角色 | 职责 |
|------|------|
| 编译者 | 读取 raw/ 资料，生成/更新 wiki/ 页面 |
| 审核者 | 审核已有 wiki 页面，提出修正或补充意见 |
| 分析者 | 基于 wiki/ 内容进行深度分析 |

## 交叉验证流程

### 1. 编译阶段
- 编译者 LLM 按照 prompts/ 模板处理 raw/ 资料
- 生成 wiki 页面，设置初始 confidence 级别

### 2. 审核阶段
- 审核者 LLM 读取同一 raw/ 资料和生成的 wiki 页面
- 将审核意见写入 `reviews/`，格式如下：

```markdown
---
target: wiki/companies/300750-宁德时代.md
reviewer: GPT-4o（或其他LLM标识）
date: YYYY-MM-DD
verdict: agree|disagree|partial
---

## 审核意见

### 一致的部分
...

### 分歧点
...

### 建议修改
...
```

### 3. 合并阶段
- 用户决定是否采纳审核意见
- 如采纳，编译者 LLM 更新 wiki 页面
- 更新 confidence 级别：多 LLM 一致 → high，有分歧 → medium/low

## 避免冲突

- 同一时间只有一个 LLM 修改同一个 wiki 页面
- 审核者只写 reviews/，不直接修改 wiki/
- 所有修改通过 git commit 记录，便于追溯

## LLM 标识

参与本项目的 LLM 在 reviews/ 和 logs/ 中使用以下标识：

- `claude` — Anthropic Claude (`claude-4.6-opus`)
- `gemini` — Google Gemini (`gemini-3.1-pro`)
- `deepseek` — DeepSeek (`deepseek-v3.2`)
- `qwen` — 通义千问 (`qwen3.5-plus`)
- `glm` — 智谱 GLM (`glm-5-turbo`)

## Agent 专家系统

除了上述 Wiki 协作模式，项目还提供了多 Agent 专家系统（`agents/`），通过 CLI 交互使用。

### 核心设计理念：感知 → 决策 → 执行 → 记忆

Lucas 遵循经典 Agent 四模块架构：

```
        ┌──────────┐
        │   感知    │  用户输入、文件系统、联网搜索、行情数据
        └────┬─────┘
             ▼
        ┌──────────┐
        │   决策    │  意图分类 → 选择 action / 研究员 → tool-use loop
        └────┬─────┘
             ▼
        ┌──────────┐
        │   执行    │  工具调用、研究员并行分析、wiki 编译
        └────┬─────┘
             ▼
        ┌──────────┐
        │   记忆    │  对话上下文、用户偏好、历史结论
        └──────────┘
```

| 模块 | 实现 | 对应代码 |
|------|------|----------|
| **感知** | 用户输入 + tool-use（list_files, read_file, search_files, recall）+ 研究员工具（web_search, get_stock_data） | `agents/tools.py`, `utils/web_search.py`, `utils/stock_data.py` |
| **决策** | dispatch 意图分类 → 选择 direct/research/compile → tool-use loop 多轮推理 | `agents/manager.py` |
| **执行** | 工具调用、研究员并行/串行分析、raw→wiki 编译 | `agents/manager.py`, `agents/researcher.py` |
| **记忆** | 三层：对话上下文（内存）、用户偏好（YAML）、历史结论（JSONL 关键词检索） | `agents/memory.py` |

### 架构

```
用户问题
  │
  ▼
Lucas（意图分析 → 任务派发 → 结果汇总）
  │
  ├─→ 基本面分析师 (fundamental)
  ├─→ 技术面分析师 (technical)
  └─→ 宏观策略师 (macro)
```

### 研究员配置（agents.yaml）

| ID | 名称 | 默认模型 | 擅长领域 |
|----|------|----------|----------|
| `fundamental` | 基本面分析师 | gemini-3.1-pro | 财务分析、估值、公司基本面 |
| `technical` | 技术面分析师 | gemini-3.1-pro | K线形态、技术指标、量价分析 |
| `macro` | 宏观策略师 | gemini-3.1-pro | 宏观经济、政策分析、行业趋势 |

### 执行模式

- `parallel` — 并行执行，各研究员独立分析（默认，限流 2 并发）
- `serial` — 串行执行，后续研究员可参考前序结果（链式推理）

Lucas 根据问题意图自动选择研究员和执行模式。

## 分析请求格式

当用户要求多 LLM 分析同一问题时，每个 LLM 独立输出分析，格式：

```markdown
---
question: 用户的问题
analyst: LLM标识
date: YYYY-MM-DD
---

## 分析

...

## 结论

...

## 置信度与依据

confidence: high|medium|low
依据：...
```

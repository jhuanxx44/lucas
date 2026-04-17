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

- `claude` — Anthropic Claude
- `gpt` — OpenAI GPT
- `gemini` — Google Gemini
- `deepseek` — DeepSeek
- `qwen` — 通义千问

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

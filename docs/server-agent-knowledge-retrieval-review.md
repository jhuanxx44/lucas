# 服务端 Agent 知识检索开源实现对比

> 调研日期：2026-07-20
> 关注问题：不授予任意 Bash 的服务端 Agent，如何实现知识库检索工具；与 Codex、mini-swe-agent 这类本地执行型 Agent 有什么本质区别；Lucas 下一步应借鉴什么。
> 结论性质：设计参考，不引入新的运行时依赖。

## 1. 结论

开源项目中存在一类与 Codex、mini-swe-agent 明显不同的服务端 Agent：Dify、RAGFlow、FastGPT。它们不会让模型获得服务器 Shell，而是把数据集、租户、权限和检索参数绑定在服务端注册的 Retrieval Tool 上，模型只决定何时调用和提供什么 query。

这些项目虽然允许模型生成 query，甚至允许生成 query 数组或关键词，但都不会把 AI 输出直接交给一个“任意词命中就返回”的扫描器。成熟实现会在服务端继续执行：

```text
Agent 生成 query/query[]
  -> 受控数据集与 metadata filter
  -> keyword/full-text/vector 多路召回
  -> 融合与去重
  -> score threshold
  -> 可选 rerank
  -> Top-K 与 Token 上限
  -> chunk + score + provenance
  -> Agent 作答
```

这解释了 Lucas 的实验结果：删除 jieba、直接相信 AI 关键词没有改善 Precision，不代表 AI 生成查询不可行；真正缺口是后端仍采用低门槛 OR 子串计分、没有最低分阈值，并且会为了凑满 `limit` 返回低相关页面。

Lucas 的产品形态更接近 Dify/RAGFlow/FastGPT，而不是 Codex/mini-swe-agent。应继续保留受控业务 Tool，不应为了“Agent 自主性”给产品 Agent 开放任意 Bash。

## 2. 固定版本与读取范围

| 类型 | 项目 | 固定版本 | 本次读取范围 |
|---|---|---|---|
| 本地最小 Agent | [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent/tree/388da74aad620a384ab47669b17c52133e30e7c3) | `388da74` | Agent/Model/Environment、LocalEnvironment、limits、trajectory |
| 本地生产 Agent | [Codex](https://github.com/openai/codex/tree/315195492c80fdade38e917c18f9584efd599304) | `3151954` | turn loop、StepContext、ToolRouter、Shell sandbox/approval、ToolOutput |
| 服务端 Agent 平台 | [Dify](https://github.com/langgenius/dify/tree/ef0115d34030eb496a1bc761b842e3bcd8f5598d) | `ef0115d` | Dataset Tool、Knowledge Retrieval、multi-dataset、rerank、metadata filter |
| 服务端 RAG/Agent | [RAGFlow](https://github.com/infiniflow/ragflow/tree/f45f03a016bdad40be088ccd7e5eec554192a1b5) | `f45f03a` | Retrieval Component/Tool、hybrid retrieval、threshold、rerank、KG/PageIndex |
| 服务端 Agent 平台 | [FastGPT](https://github.com/labring/FastGPT/tree/14ff938bcccd0d670f959e8086f7121276bb0f11) | `14ff938` | Agent Dataset Search Tool、multi-query recall、融合、过滤、rerank |

本地源码位置：

- Codex：`/Users/jinghuan/code/open_source_projects/codex`
- mini-swe-agent：`/Users/jinghuan/code/open_source_projects/mini-swe-agent`

Codex、mini-swe-agent 的 Harness 总体结论另见 `docs/agent-harness-open-source-review.md`。本文只扩展“本地开放执行 vs 服务端受控检索”这一条轴。

## 3. 两类 Agent 的根本边界

| 维度 | Codex / mini-swe-agent | Dify / RAGFlow / FastGPT |
|---|---|---|
| 主要运行位置 | 用户工作区、本地或隔离容器 | 长期运行的服务端、多租户应用 |
| 默认问题类型 | 修改代码、运行测试、操作文件 | 问答、业务流程、知识库与外部服务调用 |
| 模型主要动作 | 生成命令、patch 或通用工具调用 | 调用预注册业务 Tool/Workflow Node |
| 资源发现 | `ls`、`rg`、`find`、Shell、MCP | 服务端预先选择 dataset/tool，模型只提供 query/参数 |
| 权限模型 | 工作区 sandbox + approval；或直接交给环境 | tenant/dataset/tool allowlist + 服务端鉴权 |
| 知识检索 | 通常通过文件和命令迭代探索 | 独立 Retrieval Service，带索引、阈值、rerank |
| 返回粒度 | 命令输出、文件片段、diff | chunk + score + document/dataset metadata |
| 失败恢复 | 模型观察命令错误后换命令 | 空召回、阈值过滤、换 query、可选 workflow fallback |
| 最主要风险 | 命令副作用、越权、进程泄漏 | 跨租户数据泄漏、低质量召回、无依据作答 |

本地 Agent 的能力边界主要由环境决定；服务端 Agent 的能力边界主要由 Tool contract 和后端 Service 决定。

## 4. 本地执行型 Agent

### 4.1 mini-swe-agent：把探索能力压缩成一个 Shell Environment

mini-swe-agent 的 [DefaultAgent](https://github.com/SWE-agent/mini-swe-agent/blob/388da74aad620a384ab47669b17c52133e30e7c3/src/minisweagent/agents/default.py) 保持极小循环：

```text
model.query(messages)
  -> env.execute(action)
  -> observation message
  -> model.query(...)
```

它将 Agent、Model、Environment 分成三个 Protocol。step、cost、wall-time limit 在模型调用前检查，trajectory 在每轮 `finally` 保存。

默认 [LocalEnvironment](https://github.com/SWE-agent/mini-swe-agent/blob/388da74aad620a384ab47669b17c52133e30e7c3/src/minisweagent/environments/local.py) 直接使用 `subprocess.Popen(..., shell=True)`。模型可以用 `find/grep/cat/sed/python` 自己完成检索；工具层不需要理解“Wiki”“公司”或“知识库”。超时会杀整个进程组，避免遗留子进程。

这种设计适合：

- 固定工作区内的软件工程任务；
- 环境本身已经隔离；
- Agent 需要开放式探索未知目录；
- benchmark 可以检查最终文件状态。

它不适合直接作为 Lucas 产品路径：`shell=True` 无法表达业务授权、只读知识库、外部副作用确认和多租户数据边界。

### 4.2 Codex：保留开放工具能力，但把生产边界做进运行时

Codex 的 [turn loop](https://github.com/openai/codex/blob/315195492c80fdade38e917c18f9584efd599304/codex-rs/core/src/session/turn.rs) 仍是 model -> tool -> observation，但每次 sampling 前捕获一次 StepContext，使模型看到的 context、广告出的工具和实际工具执行共享同一请求快照。

Codex 可以提供 Shell、unified exec、apply_patch、MCP、网络和其他扩展工具。与 mini-swe-agent 不同，Shell 执行还要经过：

- sandbox permission；
- approval policy；
- network policy；
- cancellation token；
- 命令级审批判断；
- 输出截断和 telemetry preview；
- turn-scoped context 与 diff tracker。

Codex 的 [Tool context](https://github.com/openai/codex/blob/315195492c80fdade38e917c18f9584efd599304/codex-rs/core/src/tools/context.rs) 还区分模型可见结果、结构化输出和日志 preview，避免把同一份无限长原始输出同时用于所有消费者。

Codex 对 Lucas 最值得借鉴的是运行时边界，不是“给 Agent 一个 Shell”：

- immutable StepContext；
- cancellation/approval/sandbox 由代码保证；
- ToolOutput 多视图；
- 工具调用与 trace 生命周期；
- provider retry 与模型修正分离。

Codex 没有内建一个等价于 `wiki_recall` 的业务检索算法。对于本地资料，它可以用 `rg + read_file` 迭代定位；对于远程业务知识，更适合通过 MCP/connector 接入受控服务。

## 5. 服务端受控型 Agent

### 5.1 Dify：模型提供 query，服务端持有数据集与检索策略

Dify 会把配置好的 Knowledge Base 转换成 Agent 可调用的 Dataset Tool。模型的运行时参数只有一个字符串 `query`；dataset id、tenant、Top-K、score threshold、metadata filter 和 retrieval model 由服务端配置。

[DatasetRetrieverTool](https://github.com/langgenius/dify/blob/ef0115d34030eb496a1bc761b842e3bcd8f5598d/api/core/tools/utils/dataset_retriever_tool.py) 会根据数据集生成 Tool name/description，Agent 只能调用已经装配的工具。Agent 路径使用 single-dataset tool；多知识库路径可以并行召回后统一 rerank。

Dify 的检索层支持：

- keyword、semantic 等不同 retrieval method；
- 多知识库并行；
- keyword/semantic weighted score；
- Top-K 与 score threshold；
- rerank model；
- manual/automatic metadata filter；
- document chunk、score、dataset/document metadata；
- query/hit callback 与资源引用。

Dify 的经济型 keyword search 也使用 jieba，但会进一步计算 TF-IDF/cosine similarity，而不是仅做词性过滤后的布尔子串加分。高质量索引则可以使用语义检索、混合排序和 rerank。

参考：[Knowledge Retrieval 文档](https://docs.dify.ai/en/cloud/use-dify/nodes/knowledge-retrieval) 与 [DatasetRetrieval](https://github.com/langgenius/dify/blob/ef0115d34030eb496a1bc761b842e3bcd8f5598d/api/core/rag/retrieval/dataset_retrieval.py)。

### 5.2 RAGFlow：允许 Agent 产关键词，但后端执行混合检索和阈值过滤

RAGFlow 的 Retrieval Component 可以作为普通 workflow node，也可以作为 Agent Tool。Tool 的 query 描述明确要求模型提供“原请求中最重要的关键词/术语及同义词”，与 Lucas 的 AI-keywords 实验最接近。

但 [Retrieval Tool](https://github.com/infiniflow/ragflow/blob/f45f03a016bdad40be088ccd7e5eec554192a1b5/agent/tools/retrieval.py) 后面仍有完整的服务端检索层：

- keyword similarity + vector cosine similarity 加权；
- 默认 similarity threshold 0.2；
- 默认 Top-N 8；
- 可选 rerank model；
- metadata filter；
- cross-language query translation；
- dataset/memory 两种受控来源；
- knowledge graph 多跳检索；
- PageIndex/目录增强；
- component timeout 与 cancellation；
- chunk、score、doc aggregation 和 reference。

因此 RAGFlow 不是“相信 AI 关键词就够了”，而是“AI 负责表达检索意图，服务端负责候选质量和权限”。

参考：[Retrieval Component 文档](https://ragflow.io/docs/retrieval_component)。

### 5.3 FastGPT：Agent 直接产 query 数组，后端多路召回与融合

FastGPT 的 [Agent Dataset Search Tool](https://github.com/labring/FastGPT/blob/14ff938bcccd0d670f959e8086f7121276bb0f11/packages/service/core/ai/llm/agentLoop/domain/systemTool/datasetSearch/index.ts) 允许模型输出字符串数组：

```json
{
  "query": ["公司名称", "时间范围", "需要查找的信息"]
}
```

服务端会规范化 query 数组，并将数据集范围留在 workflow/app 配置中。后续 [Knowledge Search Pipeline](https://github.com/labring/FastGPT/blob/14ff938bcccd0d670f959e8086f7121276bb0f11/packages/service/core/dataset/search/defaultRecall/index.ts) 不直接把这些字符串当最终结果，而是：

1. 对多条文本 query 并行执行 embedding recall 和 full-text recall。
2. 按配置权重融合两路结果。
3. 对多 query、多模态来源使用加权/RRF 融合。
4. 去除重复 chunk。
5. 根据 similarity threshold 过滤。
6. 可选 rerank，并在 rerank 失败时回退原召回结果。
7. 按最大 Token 数裁剪最终 context。
8. 返回 chunk 内容、score、引用和 usage。

并行召回见 [multiQueryRecall](https://github.com/labring/FastGPT/blob/14ff938bcccd0d670f959e8086f7121276bb0f11/packages/service/core/dataset/search/defaultRecall/multiQueryRecall.ts)，精排见 [rerank](https://github.com/labring/FastGPT/blob/14ff938bcccd0d670f959e8086f7121276bb0f11/packages/service/core/dataset/search/defaultRecall/rerank.ts)。

FastGPT 证明“模型直接提供 query 数组”可以成立，但前提是后端存在多路召回、阈值、去重、Token 预算和可观测 usage。

## 6. 对 Lucas 实验结果的解释

Lucas 已完成两轮相关实验：

1. `wiki_recall` vs filesystem-only：专用工具 9/9，filesystem-only 8/9；专用工具 Steps、Tool calls、Tokens 和成本明显更低。
2. jieba vs AI 显式关键词：两组均 9/9，但 AI 关键词的平均候选 Precision 从 0.611 降至 0.500，Token 和成本略增。

第二个实验不能推出“应该永远使用 jieba”。AI 版失败的因果链是：

```text
模型产生更多宽泛关键词
  + 任一关键词命中即可得分
  + 没有最低 score threshold
  + 索引命中不足时继续全文扫描
  + 尽量补满 limit
  = 更多干扰页面
```

RAGFlow 和 FastGPT 同样允许 AI 提供关键词/query 数组，却没有同样依赖低门槛 OR 匹配。它们通过混合召回、融合、阈值和 rerank 把“理解问题”和“决定候选质量”分开。

当前 `wiki_recall` 还存在这些结构差距：

| 能力 | Lucas 当前 | 服务端标杆 |
|---|---|---|
| Query | AI 生成字符串，工具再 jieba 过滤 | AI query/query[]；可选 rewrite/translation |
| 检索单元 | 整个 Markdown 页面 | chunk/parent-child chunk |
| 精确入口 | `index.md` 名称/分类 | dataset/metadata/entity routing |
| 关键词检索 | 文件名/正文子串简单加分 | full-text、TF-IDF/BM25 类稀疏检索 |
| 语义检索 | 无 | embedding 通常可选 |
| 多路融合 | 无 | weighted score/RRF |
| 最低阈值 | 无 | similarity/score threshold |
| 返回规则 | 尽量补满 limit | 只保留过阈值 Top-K |
| 精排 | 无 | rerank 可选、失败可回退 |
| 上下文预算 | 每页 3000 字符 | 最终 chunk Token budget |
| 可观测性 | 页面路径、正文 | score、matched source、document/chunk metadata、usage |

## 7. Lucas 建议路线

### 7.1 保持的边界

- 产品 Agent 不开放任意 Bash。
- `wiki_recall` 继续作为服务端受控业务 Tool，TaskSpec/产品配置决定是否授权。
- 模型只决定调用时机和 query；wiki root、可读范围、Top-K 上限和输出预算由代码保证。
- filesystem-only 保留为 Eval 对照组，不作为默认产品路径。
- Tool observation 必须带 provenance，不能只返回无来源文本。

### 7.2 下一轮最小实验：先过滤，不先上向量库

下一个单变量应是：

```text
current
vs
score threshold + 不再强行补满 limit
```

最小实现只需：

1. 每个候选输出确定性 score、matched keywords 和来源阶段（index/fulltext）。
2. 索引精确实体命中赋予明确高分。
3. 全文候选设置最低分数或相对 top-score 阈值。
4. 没有候选过阈值时返回空，不用低分页面补齐数量。
5. observation 只返回过阈值页面，并记录候选数、过滤数和字符数。

先在现有 WIKI-01～03 上验证行为，再增加：相似公司/相似数字干扰、无答案、正文深处事实、同义改写和多页综合任务。主要指标为 success、Precision@K、Recall@K、返回字符、Steps、Tokens 和无依据作答率。

### 7.3 第二轮候选：精确索引 + BM25/full-text chunk

只有阈值仍无法处理词频和排序时，再实验：

```text
index/entity exact recall
  + BM25/full-text chunk recall
  -> merge/dedupe
  -> threshold/Top-K
```

这一步仍可完全本地、确定性重建，不需要向量数据库。索引属于 `wiki/` 的派生产物，必须记录源页面 hash/mtime，能重建和检测过期，不能写入 `raw/`。

### 7.4 第三轮候选：embedding 与 rerank

只有固定同义改写任务证明 BM25 缺少语义召回，才加入 embedding；只有候选召回充分但排序仍差，才加入 rerank。两者分别作为单变量实验，避免一次改动同时改变 query、recall 和 ranking。

## 8. 不直接复制的部分

- 不复制 mini-swe-agent 的 `shell=True` 到产品路径。
- 不复制 Codex 的整体模块规模或桌面交互复杂度。
- 不为三道小任务引入 Dify/RAGFlow 的多租户数据库和完整向量基础设施。
- 不一次实现 FastGPT 的多模态、query extension、embedding、RRF、rerank 全链路。
- 不把 Score Threshold 只做成配置项；必须先在固定任务上找到合理语义和失败案例。

Lucas 应复制的是职责边界：

```text
模型表达检索意图
服务端决定权限和候选质量
Eval 判断最终任务是否完成
Trace 解释 query、候选、过滤和成本
```

而不是复制某个项目的完整技术栈。

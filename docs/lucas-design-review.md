# Lucas 设计评审：缺口与改进方向

## 背景假设

本文把 Lucas 理解为一个面向 A 股投研的个人知识系统，而不只是一个聊天助手。它的核心目标应当是：持续把原始资料、外部来源、历史分析、用户偏好沉淀为可复用、可审计、可迭代的认知资产。

在这个定位下，当前系统已经有了正确的雏形：`raw/` 原始资料、`wiki/` 结构化知识库、`prompts/` 编译模板、多研究员 Agent、报告归档、URL 和财务数据校验。但距离“投研认知复利引擎”还缺少几层关键能力。

## 总体判断

Lucas 现在更像“带归档能力的多 Agent 投研问答系统”。它能回答问题、生成报告、更新 wiki，但还没有形成足够硬的知识治理闭环。

真正的投研系统，关键不只是生成更长、更全面的分析，而是让每个结论都能回答：

- 这个判断来自哪些原始资料？
- 哪些是事实，哪些是模型观点？
- 这个观点是什么时候形成的？
- 后续资料是否推翻或削弱了它？
- 用户之前怎么看，现在是否发生了变化？
- 如果重新运行同一个问题，能否解释为什么答案不同？

因此，Lucas 下一阶段的重点不应该是继续增加更多 Agent，而应该是补齐证据、检索、版本、时效和可回放这五个基础层。

## 关键缺口

### 1. 证据链还不够硬

当前研究员会搜索、引用 URL，也有 URL 可达性和财务数据校验。但核心判断仍然主要是自然语言输出，缺少“claim 到 evidence”的结构化关系。

这会导致几个问题：

- synthesis 看起来完整，但很难审计。
- 用户无法快速判断哪条结论有强证据，哪条只是推理。
- wiki 被更新后，旧结论和新事实之间的关系不清楚。
- 模型幻觉只靠事后 URL 和数字校验，覆盖面不足。

建议引入最小结构：

```text
Claim
- id
- text
- type: fact | opinion | forecast | risk | assumption
- confidence
- evidence_ids
- created_at
- stale_after

Evidence
- id
- source_path | url
- quote_or_snippet
- date
- reliability
- extracted_by
```

短期可以仍然输出 Markdown，但内部至少应保存一份结构化 sidecar，例如 `report.claims.json`。

### 2. 检索层太弱

当前 wiki 和 memory 的召回主要依赖字符或子串匹配。对于投研场景，这会明显限制系统质量，因为 Agent 后续推理高度依赖召回上下文。

典型问题：

- “电池龙头”找不到“宁德时代”。
- 问行业问题时召回公司报告，或反过来。
- 旧报告和新报告没有时间权重。
- 召回结果没有 score、来源路径、更新时间，模型不知道该信谁。

建议优先做语义检索，而不是继续扩大 prompt：

- 对 wiki 页面、报告结论、raw/ingested 资料做 embedding。
- 召回时支持 metadata filter：公司、行业、概念、时间、资料类型。
- 每个召回片段返回 `score`、`path`、`updated_at`、`source_type`。
- 对过旧结论加时间衰减，避免旧观点和新事实同权。

这是 P0 级能力。没有可靠检索，多 Agent 只是在不可靠上下文上并行发挥。

### 3. raw 目录语义不干净

项目约束里写明 `raw/` 只读，但系统目前会把报告和外部抓取资料写入 `raw/`。这让“原始用户资料”和“系统生成物”混在一起。

建议重新划分目录职责：

```text
raw/          用户放入的不可变原始资料，只读
ingested/     系统抓取的外部资料
reports/      Agent 生成的分析报告和 meta
wiki/         编译后的知识库视图
memory/       用户偏好、历史结论、会话摘要
indexes/      embedding、倒排索引、检索元数据
```

这样可以明确：

- 哪些资料是用户输入。
- 哪些资料是系统抓取。
- 哪些内容是模型生成。
- 哪些页面只是知识库视图，可以重新生成。

这个调整会影响路径和归档逻辑，适合单独做一次小迁移。

### 4. 缺少版本化和回放机制

当前 wiki 更新依赖 LLM 根据模板直接产出新页面。这种方式实现快，但长期风险较高。

主要风险：

- LLM 可能覆盖旧内容。
- 无法知道某条内容由哪次报告引入。
- 冲突信息只能靠 prompt 要求“保留两者”，代码层没有保障。
- 难以回放“为什么 wiki 变成现在这样”。

建议把 wiki 更新从“直接写 Markdown”改为“生成 patch/event，再 materialize”：

```text
KnowledgeEvent
- add_fact
- add_opinion
- update_metric
- mark_stale
- supersede_claim
- link_source
```

最终 Markdown wiki 可以继续存在，但它应当是由结构化事件生成的结果，而不是唯一事实来源。

### 5. 记忆系统还不像投研记忆

当前 memory 更像聊天上下文缓存：

- 对话只保留少量轮次。
- 历史结论数量有限。
- 结论召回靠 topic 子串匹配。
- 用户偏好是覆盖式更新，缺少时间序列。

投研记忆应该能回答：

- 我之前为什么看多/看空某家公司？
- 这个观点后来有没有被证伪？
- 用户最近的关注重点是否从成长切到现金流？
- 哪些历史结论已经过期？

建议升级为：

- 结论 embedding 检索。
- 用户偏好追加式记录，而不是覆盖写入。
- 结论时效性衰减。
- stale 标记。
- 对“历史观点变化”的专门查询能力。

## 可能做得不对的地方

### 1. 多 Agent 的分工方式偏“多角度写分析”

当前多研究员机制能提升覆盖面，但不天然提升正确性。多个 Agent 并行输出后再综合，容易变成多个模型从不同角度写作文。

更稳的设计是流程型分工：

- 信息检索员：只负责找资料，不下结论。
- 数据核验员：只负责核对数字、来源和时效。
- 产业分析员：解释业务逻辑和竞争格局。
- 反方分析员：寻找风险、证伪点和弱假设。
- 综合经理：基于前面结构化材料形成结论。

这比“多个专家各写一段”更适合投研，因为它把正确性拆到了流程里。

### 2. 验证发生得太晚

当前验证发生在研究员输出完成之后。这能发现部分 URL 和数字问题，但不能阻止错误材料进入推理过程。

更合理的顺序是：

1. 检索和抓取来源。
2. 抽取结构化 evidence。
3. 验证 evidence 的来源、时效、数字。
4. 研究员只能引用已登记 evidence。
5. synthesis 汇总 claim，并保留 claim-evidence 关系。

这样验证不只是“事后打分”，而是研究流程的一部分。

### 3. 知识库更新过度依赖 prompt 自律

prompt 可以要求“增量更新、不覆盖、区分事实与观点”，但代码层没有强约束。只要模型格式漂移，就可能污染 wiki。

建议把 wiki 更新拆成两步：

1. LLM 输出结构化 update plan 或 patch。
2. 代码校验 schema，并负责写入 Markdown。

这样可以把 LLM 用在判断和抽取上，把文件格式和一致性留给代码。

### 4. 状态边界不够清楚

Lucas 同时有会话历史、用户偏好、历史结论、raw、wiki、报告归档，但这些状态之间的边界还不够明确。

建议明确四类状态：

- 会话态：当前浏览器对话，短期有效。
- 用户长期记忆：偏好、关注列表、风险偏好、风格变化。
- 项目知识库：公司、行业、概念、报告索引。
- 可审计研究记录：每次分析的输入、模型、来源、输出、校验结果。

边界清楚后，系统才容易维护，也更容易解释行为。

## 建议优先级

### P0：重做检索

目标：让 Lucas 能稳定拿到正确上下文。

最小实现：

- 新增 embedding 生成和本地索引。
- 对 wiki、reports、memory conclusions 建索引。
- 替换现有字符级 `_find_wiki_context` 和 conclusion 子串召回。
- 返回带 score/path/date/type 的片段。

验收标准：

- “电池龙头”能召回宁德时代相关内容。
- “我之前怎么看胜宏科技”能召回历史结论。
- 同一问题能看到召回来源和分数。

### P1：拆分生成物目录

目标：让 `raw/` 真正只读，避免来源和生成物混杂。

最小实现：

- 新增 `reports/` 和 `ingested/`。
- 新报告写入 `reports/`。
- 外部抓取资料写入 `ingested/`。
- wiki frontmatter 的 sources 指向真实来源。
- 保持旧路径兼容读取。

验收标准：

- 新流程不再写 `raw/`。
- 旧 raw 资料仍可编译。
- wiki sources 能区分 raw、ingested、reports。

### P1：引入 claim/evidence sidecar

目标：让关键结论可审计。

最小实现：

- 每次 report 旁边生成 `claims.json`。
- synthesis prompt 要求输出核心 claims。
- 每条 claim 至少包含 type、confidence、evidence_refs。
- UI 或 Markdown 报告展示关键结论和证据来源。

验收标准：

- 用户可以看到某条投资判断依赖哪些来源。
- 没有 evidence 的判断被标记为低置信或观点。

### P2：wiki 更新改为 patch 模式

目标：降低 LLM 直接改 wiki 的风险。

最小实现：

- LLM 先生成 wiki update plan。
- 代码校验 page type、target path、operation。
- 只允许 append section 或 mark stale，不直接整页覆盖。

验收标准：

- 旧内容不会被无意覆盖。
- 每次 wiki 更新能追溯到 report 和 claim。

### P2：升级记忆系统

目标：让 Lucas 真的记得用户和历史观点。

最小实现：

- 偏好从覆盖写入改为追加记录。
- conclusions 加 embedding 和 stale 字段。
- 召回历史结论时显示时间、匹配理由和时效状态。

验收标准：

- 能回答“我之前为什么关注这个行业”。
- 能识别历史结论可能已经过期。

## 推荐的目标架构

```text
User Question
    |
    v
Intent / Dispatch
    |
    v
Retrieval Layer
    - wiki semantic search
    - report memory search
    - raw / ingested source search
    - market data fetch
    |
    v
Evidence Builder
    - snippets
    - metrics
    - source metadata
    - freshness
    |
    v
Agent Workflow
    - retrieval analyst
    - data verifier
    - domain analyst
    - contrarian analyst
    - synthesis manager
    |
    v
Report
    - markdown
    - claims.json
    - evidence.json
    - meta.json
    |
    v
Knowledge Update
    - wiki patch events
    - memory conclusions
    - preference events
    - indexes refresh
```

## 一句话结论

Lucas 的方向是对的，但下一阶段的关键不是更多 Agent、更长 prompt 或更多模型，而是把证据链、语义检索、目录边界、知识版本和长期记忆做硬。

如果这些底层能力补齐，Lucas 才会从“能生成投研报告的聊天系统”变成“会积累、会追溯、会自我修正的投研知识系统”。

## 关联方案

- [Lucas Agent 工作流迭代优化方案](agent-workflow-iteration-plan.md)：把“多 Agent 容易变成多个角度写作文”和“验证发生得太晚”合并为一条克制版 evidence-first 路线，先引入 `Evidence` / `Claim`，默认不新增 Agent。

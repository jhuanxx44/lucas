---
llm-weight: heavy
---

你在为 Wiki 检索实验构造固定查询。只能使用下方页面内容，不得依赖模型记忆补充事实。

请输出 JSON 对象：

```json
{"queries":[{"query":"自然语言问题","type":"company_fact|concept|cross_document|near_distractor|long_tail|synonym|insufficient_evidence","answer":"仅由页面支持的参考答案；证据不足题写无法从知识库确定","relevant_paths":["路径"],"rationale":"为何这些页面是必要证据"}]}
```

要求：

- 严格生成 {query_count} 条，覆盖这些类型序列：{query_types}；顺序必须一致。
- `company_fact`、`concept`、`near_distractor`、`long_tail`、`synonym` 使用 1 个必要页面；`cross_document` 使用 2 个必要页面。
- `insufficient_evidence` 的问题要与给定实体有关，但答案所需的细节在页面中确实不存在，`relevant_paths` 必须为空。
- 问题应像真实用户提问，不要出现文件路径、来源编号、实验、页面或“根据材料”等字样。
- 不要仅问标题是什么；优先问定义、特点、时间、关系、差异或需要综合的事实。
- 同义词题可用常见中英文名或缩写，但答案必须能由页面直接支持。
- 参考答案中的每个事实都必须在必要页面中找到。
- 只输出 JSON。

候选页面：

{pages}

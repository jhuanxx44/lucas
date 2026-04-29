# TODO

## P0：记忆系统 — 语义检索

当前结论检索和 wiki 上下文召回都是子串匹配，噪音大且无语义理解（"电池龙头"找不到"宁德时代"）。

方向：
- 引入 embedding 模型（Gemini embedding 或本地模型）
- 结论和 wiki 内容向量化，余弦相似度召回
- 存储：轻量级 numpy + json，后续可换 chromadb

## P1：对话摘要压缩

当前对话上下文只保留最近 5 轮，早期信息直接丢失。

方向：超过阈值时用 LLM 压缩早期对话为摘要，保留关键结论和偏好。

## P1：研究员错误恢复

某个研究员 API 超时/限流时，整个 `_run_parallel` 会挂。需要 per-researcher try/catch，让其他研究员结果照常返回。

## P2：偏好时间序列

当前偏好覆盖写入，无法追溯用户兴趣变化。改为追加记录，Manager 可感知兴趣迁移。

## P2：结论时效性衰减

结论无权重无衰减，3 个月前的过时分析和昨天的同等对待。加时间衰减权重，过期标记为 stale。

## P2：Wiki 全文搜索

当前 `_find_wiki_context` 逐字符匹配，可与记忆系统共用 embedding 检索。

## P3：产品化分发

当前纯 Python CLI。长期方向：Python 做 HTTP server（AI + 数据源），TS CLI 做客户端，npm 全局安装。现阶段不需要。

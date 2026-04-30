---
llm-weight: medium
---
从综合报告中提取可追溯的核心结论 claims。

## 用户问题
{question}

## 综合报告
{synthesis}

## 可用 evidence
{evidence_summary}

## 要求

- 只提取报告中的关键结论，不要新增报告没有表达的观点。
- 每条 claim 尽量关联上方 evidence id。
- 如果某条 claim 没有直接 evidence 支撑，`evidence_ids` 返回空数组，并将 `confidence` 设为 `low` 或 `unverified`。
- `type` 只能是 `fact`、`interpretation`、`forecast`、`risk`、`assumption` 之一。
- `confidence` 只能是 `high`、`medium`、`low`、`unverified` 之一。
- 最多返回 10 条 claim。

返回 JSON：
{{
  "claims": [
    {{
      "type": "interpretation",
      "text": "一句完整、可单独理解的结论",
      "evidence_ids": ["ev_001"],
      "confidence": "medium",
      "assumptions": []
    }}
  ]
}}

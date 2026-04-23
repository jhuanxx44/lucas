---
llm-weight: light
---
从本次对话中提取用户偏好变化。

## 用户问题
{question}

## 分析摘要
{summary}

## 当前用户偏好
{current_prefs}

如果发现新的关注股票、行业、风险偏好等，返回更新后的完整 JSON：
{{
  "watchlist": ["股票代码列表"],
  "focus_industries": ["行业列表"],
  "risk_preference": "conservative 或 moderate 或 aggressive",
  "analysis_style": "简洁 或 详细",
  "custom_notes": ["用户特殊偏好备注"]
}}

如果没有明显变化，返回 null。

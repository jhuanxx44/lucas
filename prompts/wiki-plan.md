<!-- llm-weight: medium — 结构化判断，需要理解内容分类 -->
你是 Wiki 编辑，需要判断本次分析报告应该更新哪些 wiki 页面。

## 分析报告
{synthesis}

## 现有 wiki 页面
{existing_pages}

## 可用页面类型
- company: wiki/companies/{{代码}}-{{简称}}.md（公司档案）
- industry: wiki/industries/{{行业名}}.md（行业概览）
- concept: wiki/concepts/{{概念名}}.md（概念/主题）

请返回 JSON 数组，每个元素：
{{
  "type": "company|industry|concept",
  "name": "页面名称（如 300750-宁德时代）",
  "action": "create|update",
  "reason": "为什么需要更新/创建"
}}

规则：
- 只列出本次分析确实涉及且有新信息可补充的页面
- 如果分析内容太泛、没有具体可落地的信息，返回空数组 []
- 不要创建信息量不足的页面

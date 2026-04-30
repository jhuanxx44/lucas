---
llm-weight: medium
---
你是 Wiki 编辑。根据以下原始资料的内容，判断应该编译成什么类型的 wiki 页面。

## 原始资料路径
{raw_path}

## 原始资料内容
{raw_content}

## 现有 wiki 页面
{existing_pages}

## 已有公司分类
{company_categories}

请返回 JSON 数组，每个元素代表一个应创建或更新的 wiki 页面：
{{
  "type": "company|industry|concept",
  "name": "页面名称（如 300750-宁德时代）",
  "action": "create|update",
  "reason": "为什么需要创建/更新"
}}

规则：
- 一份资料可能涉及多个页面（如一份研报同时涉及公司和行业）
- 公司页面用 "股票代码-简称" 命名（如 300750-宁德时代）
- 如果现有页面中已有相关页面，action 设为 update
- 如果资料信息量不足以支撑一个页面，返回空数组 []
- 公司必须归入已有分类中最匹配的类别；只有确实不属于任何已有分类时才新建分类
- 同一公司不得出现在多个分类下

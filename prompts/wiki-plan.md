---
llm-weight: medium
---
你是 Wiki 编辑。根据以下收录材料的内容，判断应该编译成哪些 wiki 页面。

## 材料路径
{source_path}

## 材料内容
{source_content}

## 候选行业（领域本体）
{industries}

## 现有 wiki 页面
{existing_pages}

## 已有公司分类
{company_categories}

请返回 JSON 数组，每个元素代表一个应创建或更新的 wiki 页面：
{{
  "type": "company|industry|concept",
  "name": "页面名称（公司用公司名，行业用行业名，概念用概念名）",
  "action": "create|update",
  "reason": "为什么需要创建/更新"
}}

规则：
- 一份材料可能涉及多个页面（如一份研报同时涉及公司和行业）
- 如果现有页面中已有相关页面，action 设为 update
- 只列出本材料确实涉及且有新信息可补充的页面；信息量不足时返回空数组 []
- 公司必须归入已有分类中最匹配的类别；只有确实不属于任何已有分类时才新建分类
- 同一公司不得出现在多个分类下

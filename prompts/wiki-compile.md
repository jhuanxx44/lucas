你是 Wiki 编辑，需要根据分析报告更新一个 wiki 页面。

## 编译模板
{template}

## 当前页面内容
{current_content}

## 本次分析报告
{synthesis}

## 任务
{task_desc}

请输出完整的更新后页面内容（包含 frontmatter）。

规则：
- 增量更新：保留已有内容，补充新信息
- 新增信息用（{today}更新）标注
- 如果新旧信息矛盾，保留两者并标注时间
- 更新 frontmatter 的 updated 日期为 {today}
- 在 sources 中追加本次分析来源
- 严格遵循编译模板的格式

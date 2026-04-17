# 编译模板：从分析报告整理 Wiki

当 Agent 系统完成一轮分析后，Manager 使用此模板将分析结果整理进 wiki 知识库。

## 整理原则

1. **增量更新**：不覆盖已有内容，只补充新信息
2. **标注时效**：新增信息标注日期来源
3. **区分事实与观点**：事实直接写入，观点标注来源模型
4. **保持格式**：严格遵循目标页面类型的模板格式

## Wiki 页面类型与路径

| 类型 | 路径 | 模板 |
|------|------|------|
| company | `wiki/companies/{代码}-{简称}.md` | compile-company.md |
| industry | `wiki/industries/{行业名}.md` | compile-industry.md |
| concept | `wiki/concepts/{概念名}.md` | compile-concept.md |

## 更新规则

### 更新已有页面
- 在对应章节追加新信息，用 `（{日期}更新）` 标注
- 如果新信息与旧信息矛盾，保留两者并标注时间
- 更新 frontmatter 的 `updated` 日期
- 在 `sources` 中追加本次分析报告路径

### 创建新页面
- 按对应类型的编译模板创建完整页面
- confidence 设为 medium（单次分析）
- 在 `sources` 中引用分析报告路径

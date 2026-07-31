# LLM 写 wiki frontmatter 的 YAML 引号陷阱：校验错误必须报根因

## 问题

Lucas 用 `write_file` 往 `wiki/` 写页面时，frontmatter 的 `summary` 若未用英文单引号包裹，且摘要含英文冒号+空格（如《Situational Awareness: The Decade Ahead》）或引号等字符，`yaml.safe_load` 解析必然失败。这是 2026-07-26 加 summary 强制校验后结构性高发的失败：A 股调研摘要里英文冒号+空格出现频率很高，模型按"summary 非空"的字面契约执行，却在 YAML 语法上被拒。

## 三个叠加的设计失误

1. **工具契约比实际校验宽松**：spec 只承诺"summary 字段非空"，实际执行是"整个 frontmatter 必须通过 yaml.safe_load"。模型按契约写必然踩坑。
2. **错误报告掩盖根因**：校验函数把 `yaml.YAMLError` 吞掉统一返回 `missing_summary`，模型看不到行/列，只能靠猜（猜对一次不代表次次猜对）。
3. **提示没教模型避坑**：spec 和 system prompt 都没提引号规则，直到修复才补上。

## 修复后的正确做法

参考实现：`harness/tools/generic/filesystem.py` 的 `_check_wiki_frontmatter`。

- 错误分类：frontmatter 缺失 → `missing_frontmatter`；YAML 解析失败 → `invalid_yaml` 并带出具体行/列和修复提示；真的缺 summary/为空 → `missing_summary`。错误信息直接指向根因，模型一次重试即可修对。
- 约束写进契约：`WRITE_FILE_SPEC` 描述与 `lucas-system-prompt.md` 都明确"summary 的值必须用英文单引号包裹"。
- 回归测试：`tests/test_write_file_wiki.py` 覆盖未加引号（复刻线上 trace 内容）、加引号、缺 summary、空 summary、缺 frontmatter、非 wiki 文件与 index/glossary 豁免、`ToolRuntime` 入口与下游 `recall_wiki` 召回。

## 通用教训

- 校验的报错必须区分"用户做错了什么"和"系统看不懂输入"，把解析器原始错误（行/列）透出给调用方（这里是 LLM）。
- 让 LLM 手写格式时，格式约束要写进工具契约和提示，不能只靠校验兜底；错误信息里的示例写法要能直接指导修复。
- 校验标准必须与下游读取端一致：下游 `wiki_recall` 同样用 `yaml.safe_load` 解析，写入时放行坏 YAML 会在召回时悄悄退化。

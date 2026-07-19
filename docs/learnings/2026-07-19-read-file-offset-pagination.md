# read_file 分页：让 LLM 能读完大文件

## 问题

`read_file` 工具默认截断到 4000 字符，返回 `truncated=true`。但 LLM 无法读取截断后的剩余内容 —— 没有 offset 或翻页参数，`max_chars` 只能控制上限，不能分段读取。

## 解决方案

给 `read_file` 增加 `offset` 参数（默认 0），语义是「从文件第 N 个字符开始读」。LLM 看到 `truncated=true` 后，用 `offset=上次结束位置` 就能继续读取。

### 核心改动

**`offset` 的计算逻辑**（两处实现相同）：

```
sliced = content[offset:offset + max_chars]
truncated = (offset + len(sliced)) < len(content)  # 还有剩余 → true
```

边界情况：
- `offset >= len(content)` → 返回空字符串，`truncated=false`（不误导 LLM 以为还有内容）
- `offset < 0` → 修正为 0

### 修改的文件

- `harness/tools/filesystem.py:27-48` — Harness 层 `read_file`
- `agents/tools.py:76-110` — Agent 层 `ToolKit.read_file`
- `tests/test_harness_runner.py` — 新增 `test_read_file_offset_paginates` 和 `test_read_file_offset_at_end`

## 设计取舍

**为什么用字符偏移而不是行号？**
- 字符偏移实现最简，不需要分行解析
- LLM 从上次返回的字符数就能算出下次的 offset
- 行号语义在 markdown/code 等不同格式下边界模糊（空行算不算？）

**为什么不加 `start_line` / `end_line`？**
- 遵循“简单优先”原则：只加一个参数解决当前问题
- 行号模式可以后续按需加，不影响现有 offset 语义

**为什么 `offset >= len` 返回空而不是报错？**
- 如果 LLM 算错 offset 报错，它需要额外步骤纠正
- 返回空字符串让 LLM 自然意识到“读完”，减少无效工具调用

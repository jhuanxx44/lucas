# Lucas — A股股市 LLM Wiki

基于 Karpathy LLM Wiki 模式构建的A股市场知识库。

## 结构

```
raw/          原始资料（只读）
wiki/         LLM编译的结构化Wiki
prompts/      编译模板
reviews/      多LLM交叉验证记录
logs/         编译日志
```

## 使用方式

1. 将原始资料放入 `raw/` 对应子目录
2. 让 LLM 编译：`"编译 raw/research/xxx.md"`
3. LLM 自动生成/更新 wiki 页面并维护索引
4. 可让其他 LLM 交叉验证

详见 [CLAUDE.md](CLAUDE.md) 和 [AGENTS.md](AGENTS.md)。

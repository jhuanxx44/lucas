# Eval 任务纵览

本文件是面向维护者的任务索引，用于快速了解每个 Eval 任务在验证什么。它不参与运行时加载；任务的可执行定义仍以各目录中的 `task.yaml` 为准，套件归属以 `evals/suites/*.yaml` 为准。

新增、删除或改变任务目标时，应同步更新本表。仅调整 fixture、期望值、步数限制等实现细节，而任务目标没有变化时，不必更新。

| 任务 | 套件 | 要求 Agent 完成什么 | 主要验证能力 |
| --- | --- | --- | --- |
| [`READ-01`](READ-01/task.yaml) | `smoke` | 读取根目录 `config.yaml`，返回其中的 provider 和 timeout，不修改文件 | 单文件读取、结构化回答 |
| [`EDIT-01`](EDIT-01/task.yaml) | `smoke` | 把 `config.yaml` 的 timeout 从 5 改为 10，同时保持其他配置和文件不变 | 精确编辑、修改范围控制、测试验证 |
| [`READ-02`](READ-02/task.yaml) | `capability` | 从约 38 万字符的招股说明书中定位研发人员表格，返回四个报告期的人数 | 长文件定位、信息提取 |
| [`READ-03`](READ-03/task.yaml) | `capability` | 在 10 份笔记中找出包含 `refresh_interval` 的文件并返回文件名和值 | 多文件搜索、目标定位 |
| [`LIST-01`](LIST-01/task.yaml) | `capability` | 递归盘点 YAML 文件，返回总数以及最大文件的路径和字节数 | 目录遍历、统计与比较 |
| [`EDIT-02`](EDIT-02/task.yaml) | `capability` | 在存在两个同名配置项时，只修改 `[server]` 段的 timeout，并返回 server/client 的最终值 | 消歧、局部精确编辑 |
| [`WRITE-01`](WRITE-01/task.yaml) | `capability` | 在 Wiki 中新建指定笔记，写入要求的标题和 IDM 说明，不修改已有文件 | 新建文件、内容约束、修改范围控制 |
| [`WIKI-01`](WIKI-01/task.yaml) | `business-capability` | 从已索引公司页面回答澄海精密的产线一次良率 | Wiki 单页事实召回 |
| [`WIKI-02`](WIKI-02/task.yaml) | `business-capability` | 从未索引公告页面回答股票代码 688559 对应公司的现金分红方案 | Wiki 未索引内容召回 |
| [`WIKI-03`](WIKI-03/task.yaml) | `business-capability` | 综合两个公司页面，比较年产能并计算差值 | Wiki 多页召回、信息综合与计算 |

## 套件定位

- `smoke`：最小读写闭环，用于快速确认 Runner、工具和 grader 基本可用。
- `capability`：文件系统通用能力，包括长文本、多文件、消歧编辑和新建文件。
- `business-capability`：Lucas 当前业务场景中的本地 Wiki 检索与综合。

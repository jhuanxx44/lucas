# Eval 任务纵览（Agent 级）

本文件是面向维护者的任务索引，用于快速了解每个 Eval 任务在验证什么。它不参与运行时加载；任务的可执行定义仍以各目录中的 `task.yaml` 为准，套件归属以 `evals/suites/*.yaml` 为准。

新增、删除或改变任务目标时，应同步更新本表。仅调整 fixture、期望值、步数限制等实现细节，而任务目标没有变化时，不必更新。

> **本目录只放 Agent 级任务。** 直接调用某个函数、不启动 Agent 的组件级实验放在
> `evals/components/`，见 [`evals/components/README.md`](../components/README.md)。
> 两类 eval 的判定标准和边界见该文件的"两类 eval 的边界"一节。

| 任务 | 套件 | 要求 Agent 完成什么 | 主要验证能力 |
| --- | --- | --- | --- |
| [`READ-01`](READ-01/task.yaml) | `smoke` | 读取根目录 `config.yaml`，返回其中的 provider 和 timeout，不修改文件 | 单文件读取、结构化回答 |
| [`EDIT-01`](EDIT-01/task.yaml) | `smoke` | 把 `config.yaml` 的 timeout 从 5 改为 10，同时保持其他配置和文件不变 | 精确编辑、修改范围控制、测试验证 |
| [`READ-02`](READ-02/task.yaml) | `capability` | 从约 38 万字符的招股说明书中定位研发人员表格，返回四个报告期的人数 | 长文件定位、信息提取 |
| [`READ-03`](READ-03/task.yaml) | `capability` | 在 10 份笔记中找出包含 `refresh_interval` 的文件并返回文件名和值 | 多文件搜索、目标定位 |
| [`LIST-01`](LIST-01/task.yaml) | `capability` | 递归盘点 YAML 文件，返回总数以及最大文件的路径和字节数 | 目录遍历、统计与比较 |
| [`EDIT-02`](EDIT-02/task.yaml) | `capability` | 在存在两个同名配置项时，只修改 `[server]` 段的 timeout，并返回 server/client 的最终值 | 消歧、局部精确编辑 |
| [`WRITE-01`](WRITE-01/task.yaml) | `capability` | 在 Wiki 中新建指定笔记，写入要求的标题和 IDM 说明，不修改已有文件 | 新建文件、内容约束、修改范围控制 |
| [`WRITE-02`](WRITE-02/task.yaml) | `capability` | 把给定营收数据真正写入已有公司档案的财务概况节，只在回复里声称"已更新"不算通过 | 反"幻觉式完成"：改动必须落盘、局部编辑、修改范围控制 |
| [`MULTI-01`](MULTI-01/task.yaml) | `planner-experiment` | 汇总四份季度报告并计算年度数据 | 跨文件读取、线性汇总 |
| [`MULTI-02`](MULTI-02/task.yaml) | `planner-experiment` | 召回三家公司并生成对比报告 | Wiki 综合、报告写入 |
| [`PLAN-01`](PLAN-01/task.yaml) | `planner-complex-experiment` | 识别三个待迁移服务，按依赖更新配置并生成部署/回滚计划 | 条件筛选、依赖排序、多文件一致性 |
| [`PLAN-02`](PLAN-02/task.yaml) | `planner-complex-experiment` | 更新三家公司档案，再生成可追溯横向报告并更新索引 | 多阶段产物依赖、证据归属、跨文件一致性 |
| [`PLAN-03`](PLAN-03/task.yaml) | `planner-complex-experiment` | 综合事故证据，只执行满足条件的处置并生成事故报告 | 条件行动、证据链、变更范围控制 |
| [`WIKI-01`](WIKI-01/task.yaml) | `business-capability` | 从已索引公司页面回答澄海精密的产线一次良率 | Wiki 单页事实召回 |
| [`WIKI-02`](WIKI-02/task.yaml) | `business-capability` | 从未索引公告页面回答股票代码 688559 对应公司的现金分红方案 | Wiki 未索引内容召回 |
| [`WIKI-03`](WIKI-03/task.yaml) | `business-capability` | 综合两个公司页面，比较年产能并计算差值 | Wiki 多页召回、信息综合与计算 |
| [`WIKI-04`](WIKI-04/task.yaml) | `wiki-retrieval-experiment` | 从五个名称和指标相似的较长公司页面中定位海岳材料的资本开支 | 相似干扰页、长页面、progressive disclosure 成本 |
| [`RETRIEVAL-01`](RETRIEVAL-01/task.yaml) | `retrieval-policy-experiment` | 查找长鑫存储科创板招股书原文并返回官方链接 | 显式原文请求的检索触发 |
| [`RETRIEVAL-02`](RETRIEVAL-02/task.yaml) | `retrieval-policy-experiment` | 在用户纠正错误事实后重新核验招股书 | 用户纠错后的事实恢复与检索 |
| [`RETRIEVAL-03`](RETRIEVAL-03/task.yaml) | `retrieval-policy-experiment` | 直接回答招股说明书披露阶段 | 稳定定义题不过度检索 |

## 套件定位

- `smoke`：最小读写闭环，用于快速确认 Runner、工具和 grader 基本可用。
- `capability`：文件系统通用能力，包括长文本、多文件、消歧编辑和新建文件。
- `business-capability`：Lucas 当前业务场景中的本地 Wiki 检索与综合。
- `wiki-retrieval-experiment`：只用于 Wiki 访问策略消融；结论稳定前不迁入 regression。
- `retrieval-policy-experiment`：验证何时应检索以及何时应直接回答；结论稳定前不迁入 regression。
- `planner-complex-experiment`：专门放置具有多阶段依赖和多个环境结果的复杂任务，供
  baseline、可选 Planner 与强制 Planner 做同条件对照；plan 调用只作为诊断指标，不参与 outcome 成功判定。

## 与线上聊天的关系

评测与线上产品聊天走**同一条执行链路**：同一个 `AgentRunner`、同一份循环模板 `prompts/harness/agent-loop.md`、同一份系统提示 `prompts/harness/lucas-system-prompt.md`、同一套工具 `ToolSpec`。

差异只在工具集，且是有意的：

- 评测 adapter（`evals/harness/adapters/lucas_single.py`）**注册全部 9 个工具**（研究工具 + 文件读写工具），因为评测要覆盖 `READ/EDIT/WRITE` 这类框架级文件操作能力——这些是线上聊天本就不开放的能力。
- 每道题再通过 `task.yaml` 的 `allowed_tools` **逐题收窄**到该题考察能力的最小集，并由 `type: allowed_tools` grader 校验 Agent 未越界。
- 线上聊天（`server/services/agent_stream.py`）是只读研究助手，**只装 4 个研究工具**（web_search / stock_quote / stock_kline / wiki_recall），不开放文件读写。

因此在共同能力（研究类）上评测与线上逐字对齐；文件类是评测额外覆盖的框架能力。修改循环模板或系统提示时，两条入口会同时受影响，需一并验证。

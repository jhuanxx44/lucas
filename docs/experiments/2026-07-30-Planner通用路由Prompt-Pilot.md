# Planner 通用路由 Prompt Pilot

日期：2026-07-30
Suite：`planner-complex-experiment-v1`
Variant：Optional Planner 通用复杂度路由候选
模型：`deepseek-v4-flash`，temperature=0
Trials：每题 1 次

## 假设与实验变量

原 system prompt 主要用“多轮调研、行业研究、多公司对比”解释 Planner，可能使模型把
`update_plan` 理解成投研专用工具。本轮假设是：改用任务结构描述触发条件，并要求计划覆盖输入、
产物、依赖和禁止事项，能让 Flash 在主要写入前主动规划，减少多产物和多约束遗漏。

本轮只替换 `prompts/harness/lucas-system-prompt.md` 中“怎么用好工具”的前四条。候选文本为：

> - 复杂、多阶段任务如果涉及多个交付物或文件、依赖顺序、条件行动、证据覆盖或多项成功约束，应在执行前先用 `update_plan`。简单单步任务不需要规划。
> - 计划按可验证的阶段结果和依赖关系拆分，覆盖必要输入、最终产物和禁止事项，不要只罗列工具调用；始终只保留一个 `in_progress` 阶段。
> - 每完成一个阶段或发现范围、依赖发生变化，就立即用 `update_plan` 更新状态，再继续执行。
> - **先收集，再产出。** 写入或下结论前先读取必要材料并核对约束；修改已有文件前先读取原内容，优先用 `apply_patch` 精确修改，避免丢失已有信息。

候选文件 SHA-256：`ed3378f2c952e8bef86a83680246941f9472f11ee0712c0f09d1af4e453b81d6`。
fixture、grader、工具、模型、temperature 和预算不变。实际配置由
`load_agent_config()` 确认为 `deepseek-v4-flash`。

当前 PLAN-02 已是一句极简开放目标，其固定路径 grader 与题面并不完全对齐，因此该题的 raw grade
只作诊断；PLAN-01/03 仍是公开完成态和禁止事项的自然题面。

## 结果

| Task | Outcome | Steps | Tool calls | Plan calls | Tokens | Cost | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| PLAN-01 | pass | 13 | 12 | 0 | 54,255 | $0.173020 | 59.12s |
| PLAN-02 | fail | 15 | 14 | 0 | 59,515 | $0.158980 | 42.30s |
| PLAN-03 | fail | 11 | 10 | 0 | 45,913 | $0.140316 | 46.74s |
| 合计 | 1/3 | 39 | 36 | 0 | 159,683 | $0.472316 | 148.16s |

对比各题当前题面最近一次 Flash baseline：

| Metric | 最近 baseline | 通用路由候选 | 变化 |
|---|---:|---:|---:|
| outcome | 1/3 | 1/3 | 无变化 |
| steps | 38 | 39 | +1 |
| tool calls | 35 | 36 | +1 |
| plan calls | 0 | 0 | 无变化 |
| tokens | 149,606 | 159,683 | +6.7% |
| cost | $0.432042 | $0.472316 | +9.3% |
| duration | 137.30s | 148.16s | +7.9% |

baseline 来源：PLAN-01/03 使用自然目标题面 Pilot；PLAN-02 使用极简题面 Flash Pilot。三题不是同质
正式 benchmark，因此合计只用于成本和触发诊断，不用于估计通用成功率。

## Trace 归因

### PLAN-01

与 baseline 一样通过。Agent 直接列目录、读规范和五个服务配置，再修改三个服务并生成发布文档；
第一步到最终回答之间没有 `update_plan`。

### PLAN-02

相较极简 baseline，这次真实创建了横向报告，但使用了合理却不被旧 grader 接受的
`wiki/reports/电子/2026Q3半导体横向比较.md`。三个公司页仍没有来源路径，`wiki/index.md` 在写入前后
各读了一次却没有修改。最终回答再次声称“更新知识库索引”，与工具调用和环境 diff 不一致。

因此这里混合了两类失败：固定报告路径属于题面/grader 不对齐；来源遗漏、索引未写却自报完成属于
真实可靠性问题。

### PLAN-03

Agent 这次读取了发布记录、指标和两份日志，补齐了旧 baseline 遗漏的 09:40 事件和证据路径；但只
实际修改了 `checkout-api`，没有调用工具修改 `order-worker`，报告和最终回答却都声称已将
`idempotency_key_required` 改为 `true`。报告使用“## 失败回滚顺序”而 grader 只接受标题紧邻
“回滚/rollback”，这部分是 grader 过窄；未实际修改 `order-worker` 是真实 outcome 失败。

## 结论与机制决策

1. 假设未获支持：更通用、更明确的 Optional Planner 路由在 Flash 上仍是 0/3 触发。
2. outcome 仍为 1/3，token、成本和延迟均未改善；单 trial 中 PLAN-02/03 的局部行为变化不能归因
   为稳定收益。
3. system prompt 的“应当规划”不足以验证 Planner 机制价值。下一步应实现 required-planner
   variant，在首个主要写入前建立计划，再做同模型对照。
4. 两个失败再次说明候选答案 validation 的必要性：Agent 声称索引或配置已修改，但环境中没有对应
   mutation。
5. Trace 尚未持久化 system prompt、Tool Spec 和 prompt hash。虽然本次由新进程直接读取候选文件，
   运行产物本身不能独立证明收到哪版 system prompt，这是后续可比较实验需要补齐的基础信息。

由于本轮没有 Planner 触发或 outcome 收益，候选 system prompt **不保留到生产版本**，实验后恢复
原文本；负结果和候选 hash 保留在本报告中。

## 原始产物

- Suite：`runs/planner-complex-experiment-v1-20260730-231807-201de92f/`
- PLAN-01：`runs/planner-complex-experiment-v1-20260730-231807-201de92f/runs/plan-01-6c8dad9968e1/`
- PLAN-02：`runs/planner-complex-experiment-v1-20260730-231807-201de92f/runs/plan-02-c66f1625a8e3/`
- PLAN-03：`runs/planner-complex-experiment-v1-20260730-231807-201de92f/runs/plan-03-c2ecc6468fb6/`

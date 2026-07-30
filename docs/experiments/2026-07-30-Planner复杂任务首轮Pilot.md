# Planner 复杂任务首轮真实模型 Pilot

日期：2026-07-30
Suite：`planner-complex-experiment-v1`
Variant：当前 `lucas-single`（Optional Planner）
模型：`deepseek-v4-flash`，temperature=0
Trials：每题 1 次

## 假设与边界

假设：多阶段依赖、多个环境产物和条件式行动会促使模型使用 `update_plan`，并暴露早期线性任务
没有覆盖的遗漏、串写或计划外修改。

本轮只做题目 pilot，不是 Planner A/B。模型可以自行决定是否调用 `update_plan`；没有运行
“无 Planner”或“强制 Planner”对照，因此不能从本轮推断 Planner 的因果收益。

## 结果

| Task | Outcome | Steps | Tool calls | Plan calls | Tokens | Cost | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| PLAN-01 | pass | 12 | 11 | 0 | 47,399 | $0.132908 | 40.70s |
| PLAN-02 | pass | 15 | 14 | 0 | 61,800 | $0.162990 | 42.30s |
| PLAN-03 | pass（grader 修正后） | 15 | 14 | 0 | 64,683 | $0.178646 | 51.48s |
| 合计 | 3/3 | 42 | 39 | 0 | 173,882 | $0.474544 | 134.48s |

三题都满足最终环境状态和修改范围要求，trace 生命周期完整，没有工具错误或重复停滞。

## PLAN-03 grader 假阴性

原始 suite summary 记录 PLAN-03 outcome fail，原因为测试从报告中第一次出现“回滚”二字的位置
开始比较服务顺序。Agent 的标题/前文先提到回滚，后面的证据列表又先出现 checkout-api，导致
测试没有定位正式的 `## 回滚顺序` 章节。

冻结 run 中的正式回滚章节实际为 `order-worker → checkout-api`，符合 runbook。修复后 grader
只匹配 Markdown 二级“回滚/rollback”标题；冻结环境按新规则复核通过，task 的 known-bad/Oracle
双向 validation 也通过。原始 run 和原始 summary 均保留，不覆盖实验事实。

## 结论

1. 三个复杂任务有真实执行压力：单题 12–15 步、11–14 次工具调用，且能确定性验收多文件结果。
2. 当前模型在三题中仍然 0 次调用 `update_plan`，说明“提供 Planner + prompt 建议”不足以触发规划；
   也可能说明这些任务虽长，但模型仍能用隐式规划完成。
3. 由于 Optional Planner 没有实际进入执行路径，本轮不能验证 Planner 是否有效，只验证了裸循环在
   首次样本中可完成三题。
4. Pilot 成功发现并修复了一个 grader 假阴性，说明正式 A/B 前先跑少量 pilot 是必要的。

## 下一步

在同一 suite 上实现两个独立 variant：

- baseline：移除 `update_plan` 和 Planner 专属 prompt；
- required-planner：复杂任务开始执行前必须先产生计划。

先各跑 3 次，与当前 Optional Planner 交错比较 outcome、steps、token、cost、遗漏与返工。若 Required
Planner 没有改善 outcome 或效率，则不应继续为 Planner 增加运行时复杂度；若 Required 有收益而
Optional 始终不触发，问题属于复杂度路由而不是 Planner 机制本身。

## 原始产物

- Suite：`runs/planner-complex-experiment-v1-20260730-224142-bc709170/`
- PLAN-01：`runs/plan-01-26735a1a941a/`
- PLAN-02：`runs/plan-02-418cc6eea53f/`
- PLAN-03：`runs/plan-03-d043615003f0/`

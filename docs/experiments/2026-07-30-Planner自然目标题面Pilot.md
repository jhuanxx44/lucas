# Planner 自然目标题面 Pilot

日期：2026-07-30
Suite：`planner-complex-experiment-v1`
Variant：当前 `lucas-single`（Optional Planner）
模型：`deepseek-v4-flash`，temperature=0
Trials：每题 1 次

## 假设与单变量

首轮复杂任务把执行步骤直接编号写进 instruction，等同于给 Agent 一份外部计划。待验证假设是：
把题面改为只描述目标、完成态和禁止事项后，Agent 会识别多阶段依赖并调用 `update_plan`；如果仍
不调用，任务遗漏和返工会增加。

本轮只改变 PLAN-01～03 的 instruction 表达。fixture、reference、grader、工具、system prompt、
模型、temperature、步数、timeout 和成本预算全部保持不变。改写后 known-bad 仍失败、Oracle 仍
通过，证明成功契约没有变化。

## 结果

| Task | Outcome | Steps | Tool calls | Plan calls | Tokens | Cost | Duration |
|---|---:|---:|---:|---:|---:|---:|---:|
| PLAN-01 | pass | 14 | 13 | 0 | 56,880 | $0.160700 | 47.74s |
| PLAN-02 | fail | 23 | 22 | 0 | 110,561 | $0.303012 | 82.68s |
| PLAN-03 | fail | 11 | 10 | 0 | 43,425 | $0.130710 | 42.98s |
| 合计 | 1/3 | 48 | 45 | 0 | 210,866 | $0.594422 | 173.40s |

与结构化题面首轮对比：

| Metric | 结构化题面 | 自然目标题面 | 变化 |
|---|---:|---:|---:|
| success | 3/3 | 1/3 | -2 tasks |
| steps | 42 | 48 | +14.3% |
| tool calls | 39 | 45 | +15.4% |
| plan calls | 0 | 0 | 无变化 |
| tokens | 173,882 | 210,866 | +21.3% |
| cost | $0.474544 | $0.594422 | +25.3% |
| duration | 134.48s | 173.40s | +28.9% |

## 失败归因

### PLAN-02：长链路遗漏来源

Agent 完成三份材料和旧档案读取、公司页更新、对比报告和索引更新，但三个公司页没有保留
`sources/2026Q3/<公司>季度简报.md` 来源路径。它运行到 23/24 步才回答，发生 22 次工具调用，
仍没有使用 Planner。失败属于多成功条件中的局部遗漏，不是工具或 grader 故障。

### PLAN-03：证据集合读取不完整

Agent 读取 runbook、指标和日志并正确修改两个配置，但没有读取 `evidence/deploy-timeline.md`。
因此事故报告缺少 09:40 发布事件和发布记录证据路径。它只用了 11 步便宣布完成，属于过早收尾。

## 结论

1. 自然目标题面成功移除了“外部预制计划”，并暴露了真实的多条件遗漏和证据覆盖不足。
2. 当前 Optional Planner 在更需要状态管理的环境中仍然 0 次触发；不能再用“任务已经预拆解”
   解释全部现象。
3. 当前 system prompt 只把“多轮调研、行业研究、多公司对比”明确描述为 Planner 场景，对多文件、
   多产物、条件行动和证据覆盖的复杂任务触发不足。PLAN-02 即使属于多公司对比仍未触发，说明
   仅提供工具和一句建议的路由强度也不够。
4. 这组任务现在具有区分度：裸循环从 3/3 降到 1/3，并付出更多步骤和成本。下一步应保持自然
   题面不变，运行 required-planner，测量显式 Planner 能否恢复两类失败。

## 下一步

不要重新给题面添加步骤，也暂不直接修改生产 prompt。先实现 required-planner 实验 variant：
只对本 suite 要求执行前建立计划，并把计划维护作为处理多个成功条件的机制。与当前 Optional
Planner 同题比较；若 Required 恢复 PLAN-02/03，再单独实验更广的复杂度路由 Prompt。

## 原始产物

- Suite：`runs/planner-complex-experiment-v1-20260730-225105-833b90fd/`
- PLAN-01：`runs/plan-01-68c70cd09022/`
- PLAN-02：`runs/plan-02-47c69df8f9e3/`
- PLAN-03：`runs/plan-03-2e377b410dbc/`

# Flash 正式版 PLAN-01～04 并发 Pilot

日期：2026-07-31
Suite：`planner-all-experiment-v1`
Variant：当前 `lucas-single`（Optional Planner）
模型：`deepseek-v4-flash`，temperature=0
Trials：每题 1 次，四题并发运行

## 假设与实验边界

待验证假设：如果 `deepseek-v4-flash` 后端正式版改善了工具路由和长任务状态维护，那么在不修改
生产 Prompt、工具、题面、grader 和预算的情况下，PLAN-01～04 应出现更稳定、更早且可持续更新的
Planner 使用，并减少多产物、来源追溯和索引遗漏。

本轮冻结条件如下：

- 模型别名：`deepseek-v4-flash`；temperature=0；四题各 1 trial。
- 生产 system prompt 未修改，SHA-256 为
  `3b4c37920f50d735839502dc1184f9d41ae89cbe2239134b41c1a6357b551296`。
- 默认模型仍为 `providers.yaml` 中的 `deepseek-v4-flash`。
- 四题用独立临时 workspace 和 trace，通过 `asyncio.gather` 并发执行；没有共享任务状态。
- Provider 没有返回可验证的后端版本号，因此“正式版”只能按相同模型别名下的新运行观察，不能把
  行为变化确定归因于某个已知模型版本。

PLAN-02 仍是一句开放目标 probe，而它的旧 grader 仍绑定固定报告名；因此继续同时报告 raw outcome
与人工复核后的 semantic outcome。

## 结果

| Task | Raw | 语义 | Steps | Tools | Plan calls | 首次 Plan / 首次写入 | Tokens | Cost | Duration |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|
| PLAN-01 | fail | pass | 20 | 18 | 4 | step 6 / 13 | 111,109 | $0.391998 | 151.97s |
| PLAN-02 | fail | fail | 22 | 20 | 3 | step 8 / 12 | 113,413 | $0.341056 | 95.57s |
| PLAN-03 | pass | pass | 15 | 13 | 0 | — / 11 | 70,409 | $0.225638 | 78.97s |
| PLAN-04 | pass | pass | 21 | 20 | 3 | step 4 / 14 | 154,010 | $0.582730 | 221.74s |
| 合计 | 2/4 | 3/4 | 78 | 71 | 10 | — | 448,941 | $1.541422 | 并发墙钟约 222s |

各任务 duration 高度重叠，适合检查本轮 timeout 和单题行为，不应与旧串行 suite 的 duration 合计
直接比较。并发墙钟由最早启动到最晚完成计算，基本由 PLAN-04 决定。

## Planner 路由和维护

| Task | 计划内容与状态变化 | 过程判断 |
|---|---|---|
| PLAN-01 | step 6 建立“读取→迁移→rollout→回答”；step 11/17/19 推进阶段状态 | 主干完整，但启动前已读两个配置；4 次调用占满 20 步预算的 20%，没有最终验证步骤 |
| PLAN-02 | step 8 建立“旧档案→公司页→报告→索引→回答”；step 17/21 更新 | 推动报告和索引真实落盘，但把“可追溯”弱化为泛化来源标注，未覆盖具体文件路径 |
| PLAN-03 | 未调用 | 证据读取、条件处置、报告和回滚均完整通过，说明显式 Planner 不是所有复杂题的必要条件 |
| PLAN-04 | step 4 在写入前建立“收集→档案→报告→索引→核对”；step 13/17 更新 | 收集与产出阶段清晰，关键成功条件覆盖最好；最终没有再更新，计划仍停在报告进行中、索引待办 |

三条有 Plan 的任务都不再是“一次性打卡”：PLAN-01/02/04 分别更新 4/3/3 次。这是相对旧 Flash
最明显的变化。但计划维护仍有共同缺口：没有独立的最终环境验证，且最终 answer 前没有把计划全部
收口为 completed。

## 分题归因

### PLAN-01：raw 假阴性，语义通过

三个合格服务配置、业务字段、部署门槛和逆序回滚全部正确。原测试从正文第一次出现“回滚”二字
开始截取；文档导语先写“部署、验证与回滚方案”，所以测试误把后面的部署正序当成回滚顺序。
独立 `## 回滚` 章节实际为 notification-api → billing-worker → auth-gateway。

grader 已改为定位包含“回滚/rollback”的 Markdown 标题后再判断顺序；PLAN-01 known-bad 仍失败、
Oracle 仍通过。原 workspace 已由 Harness 清理，无法在原冻结目录直接重判，因此 raw result 保留为
fail，报告按 trace 中的完整落盘内容记 semantic pass。

Planner 对范围和阶段推进有帮助，但 4 次调用也让任务正好用满 20 steps。此次失败与步数无关，产物
已经完成；只能说存在预算压力，不能说 Planner 伤害了 outcome。

### PLAN-02：真实失败，Planner 未覆盖核心约束

模型读取三份正式材料和旧档案，正确更新 Q3 数字并保留旧风险，也真实创建横向报告、更新索引。
相较旧 Flash 的“只写公司页却声称报告和索引已完成”，后半段交付明显改善。

但三个公司页没有各自的具体 source path，报告只引用 `sources/2026Q3/` 目录；这不满足“可追溯”
核心目标。报告名 `2026Q3半导体对比.md` 还偏离 grader/allowed path 所要求的
`2026Q3半导体公司对比.md`。即使剔除固定文件名不对齐，具体来源缺失仍使 semantic outcome 失败。

计划把来源要求写成“含数据来源标注”，没有拆成逐公司路径、关键 claim 绑定和最终核对。它还在
三家公司页写完后才读取声称应在第一阶段读取的 Q2 报告，说明 Plan 状态没有完全约束实际行为。

### PLAN-03：无 Planner 仍稳定通过

模型读取发布记录、指标、日志、runbook 和三个生产配置，正确修改 checkout-api 与 order-worker，
保持 inventory-api 不变，并生成包含证据、验证命令和逆序回滚的事故报告。step 12 遇到一次 provider
空输出，下一轮自行恢复。pytest 2/2，人工复核未见 grader 假阳性。

该结果说明路由没有机械地让所有长任务规划；对于证据链清晰、条件行动较线性的处置题，裸循环仍能
成功。不能把“不触发 Planner”本身当成缺陷。

### PLAN-04：本轮最强的 Planner 正向过程证据

模型在首次写入前创建计划，随后读完三份半年报摘要、估值快照、三份旧公司档案、索引和测试，再按
公司页→报告→索引执行。三份具体 source path、原风险、增长/盈利/现金/估值计算和索引均正确，
pytest 4/4；step 20 还主动补上衡星电气 `-0.20x` 净现比。

这与旧 Flash/Pro 在 PLAN-04 上出现的漏具体来源、丢风险或漏索引形成明显对比，说明 Planner 与本次
成功过程高度相关。但它仍是单次、无 Planner 开关的观察，且模型整体能力可能已经变化，不能据此
声称 Planner 产生了因果收益。

## 与旧 Flash、Pro 的方向性比较

| Metric | 旧 Flash 最近可比运行 | Pro PLAN-01～04 | 本轮 Flash |
|---|---:|---:|---:|
| 语义 outcome | 1/4 | 2/4 | 3/4 |
| 触发 Planner 的任务 | 1/4 | 2/4 | 3/4 |
| Plan calls | 1 | 2 | 10 |
| Steps | 56 | 58 | 78 |
| Tool calls | 52 | 53 | 71 |
| Tokens | 241,660 | 267,717 | 448,941 |
| Cost | $0.707710 | $0.845454 | $1.541422 |

旧 Flash 和 Pro 为此前各题最近 trial 的方向性对照，任务题面并不完全同质；本轮与 Pro 使用相同
当前四题，但仍只有每题 1 trial。duration 因本轮并发、旧运行串行而不列入比较。

本轮同时出现更高 outcome、更广 Planner 路由和明显更高步骤/token/成本。新增步骤主要来自更多读取、
产物补齐和 10 次 Planner 调用，不能只解释为低效；但在成功率被多 trial 证实之前，也不能认为这些
额外成本已经获得稳定回报。

## 结论

1. **Planner 路由发生了实质方向变化。** 新运行在 PLAN-01/02/04 三题触发并持续更新，而旧 Flash
   最近四题只有 PLAN-04 一次调用，Pro 也只有两次一次性调用。
2. **语义 outcome 从旧 Flash 的 1/4 提升到 3/4。** PLAN-01 raw fail 是新发现的 grader 假阴性；
   PLAN-04 则是真正满足具体来源、旧风险、报告和索引的成功。
3. **仍不能验证 Planner 的因果价值。** 模型后端可能同时改变了规划路由和基础执行能力；没有同一
   后端下 optional / required / disabled 的交错对照。
4. **计划质量比调用次数更关键。** PLAN-04 覆盖具体输入和全部交付物后成功；PLAN-02 虽更新三次，
   但没有把“可追溯”展开为具体文件路径，最终仍失败。
5. **Planner 有成本和预算压力。** 本轮 steps、tokens 和成本显著增加，PLAN-01 正好用满 20 steps；
   后续应把验证/收口纳入计划，同时避免过密状态更新挤占执行预算。
6. **不要强制所有复杂任务都规划。** PLAN-03 无 Planner 通过，说明路由应考虑任务结构和失败风险，
   不能只按文件数或步数触发。

## 待解决问题

### P0：做可归因的 Planner 对照

- 在当前 Flash 后端和冻结题面上增加 disabled / optional / required-planner 三个 variant，交错运行，
  每题至少 3 trials。
- required variant 要求首次 mutation 前规划，覆盖公开成功条件、禁止事项、具体证据和最终验证；不应
  规定固定工具路径。
- 单独记录 plan 创建时机、成功条件覆盖率、状态更新、计划偏离、验证恢复和净新增 token/steps。

### P0：修正 Eval 契约

- PLAN-01 回滚章节定位假阴性已经修复并通过 known-bad/Oracle。
- PLAN-02 应把固定报告名改为“存在一个被索引、包含三家公司和具体来源的 Q3 横向报告”；开放目标
  probe 不应隐藏固定路径要求。
- Task manifest 应持久化模型后端版本（若 provider 提供）、system prompt/tool spec/task hash 和请求
  形态，避免相同模型别名下的后端变化无法确认。

### P1：最终验证与预算

- Plan 应包含独立的环境核对步骤，并在 answer 前完成状态收口；不能用 summary 代替真实验证。
- 候选答案 validation 检查报告、索引、具体来源路径和禁止变更，再允许完成或进行一次有限 revision。
- 重新校准 Planning step 是否与执行 step 共用硬上限；至少应让 required Planner 的必要维护不会挤掉
  最终验证，同时记录其真实成本。

## 原始产物

`runs/planner-all-experiment-v1-parallel-20260731-154144-de84960a/`

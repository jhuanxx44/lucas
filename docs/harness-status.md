# Lucas Harness 现状与未完成项

日期：2026-08-07
定位：本文件取代 `docs/agent-harness-learning-roadmap.md`（已归档到 `docs/archive/`）作为
Harness 工作的唯一现状依据。**只记录当前是什么、还缺什么、下一个假设是什么**，不再维护
Phase 0～9 的阶段顺序。

为什么弃用阶段顺序：实际执行早已不按 Phase 走（Phase 1 基本跳过，Phase 2/4 先做完，Phase 3
一步没动），而项目并未因此变差——真正有价值的结论都来自"跟着失败数据走"，不来自阶段依赖。
归档文档仍可查阅其中的设计细节（ToolSpec 字段设想、Retry 分类表、Replay 面板清单、
Skill 接入原则、Wiki 访问策略消融设计），但**其阶段编号、完成度评级和 5.3 能力总表已过期，
不再作为计划依据**。

---

## 1. 已经具备的能力（不要重复建设）

以下均已落地、有测试、跑过真实 run：

| 能力 | 实现位置 |
|---|---|
| 统一 Agent 循环（Responses 原生 function calling） | `harness/runner.py` |
| 全量消息回放（message/function_call/reasoning 都是历史一等条目） | `harness/runner.py` `append_model_items` |
| 单轮工具调用（上限 4；只读工具并行、写入工具串行，按 call_id 原序回传） | `harness/runner.py`、`harness/tools/base.py` |
| 分级链式上下文压缩（低损丢弃 → LLM 摘要 → FIFO 兜底） | `harness/runner.py` `compress_context` |
| run / model_call / tool_call 三层 deadline 与结构化 finish_reason | `harness/runner.py` `await_before_deadline` |
| provider retry（3 次，指数等待，独立 trace 事件） | `utils/llm_client.py` |
| 模型协议 correction（上限 3）与重复失败签名拦截、停滞检测 | `harness/runner.py` |
| JSON Schema 校验的工具入参 + 结构化 `ToolResult`（5 态） | `harness/tools/registry.py`、`base.py` |
| 哑工具式 Plan（`update_plan`，observation 回显全文） | `harness/tools/generic/planning.py` |
| append-only versioned trace（25 类事件）+ artifact 落盘 | `harness/trace.py`、`evals/harness/trace.py` |
| Eval Harness：fixture 隔离、workspace 快照 diff、run 目录、manifest | `evals/harness/` |
| 三层确定性 grader（outcome / safety / process）+ trace 完整性校验 | `evals/harness/grader.py` |
| Oracle / known-bad 双向自验 | `evals/harness/validation.py`、`adapters/oracle.py` |
| 23 个 Agent 级任务、12 个 suite、组件级 eval 独立目录 | `evals/tasks/`、`evals/suites/`、`evals/components/` |
| 生产聊天与 eval 共用同一 Runner / prompt / 工具 spec | `server/services/agent_stream.py`、`evals/harness/adapters/lucas_single.py` |

347 个测试通过。归档文档 5.3 表里"L2 / 40%"的评级已不适用。

---

## 2. 已经拿到的机制结论（不要推翻重做）

这四条是可迁移的真知识，后续设计应建立在它们之上：

1. **压缩成败由任务形状决定，不由触发频率决定。** 状态外化型任务（抽完即写盘、原文不再
   需要）压缩近乎免费——CTX-01 累计输入 token 降 69.1%、重读 0 次；交叉综合型任务
   （读完全部才横向比较，如 PLAN-01）压缩必然引发重读，token 反升 23%。
   报告：`docs/experiments/2026-08-04-context-compression-long-task.md`
2. **plan 调用与成功不正相关。** Planner 触发次数、触发时机与 outcome 通过之间没有稳定
   关系；Pro 模型上出现"0 Planner 的题通过、1 Planner 的题失败"。问题不在"想没想清楚"。
   报告：`docs/experiments/2026-07-30-Planner复杂任务阶段总结.md`
3. **LLM 摘要那次调用在长任务上划得来。** level1（纯机械挖空）只降 53.7% 且步数 18→30，
   trace 显示它在写汇总前把 12 份 extracts 逐个重读；level2（含 LLM 摘要）降 69.1%、重读 0。
4. **检索上简单方法在当前规模已够用。** BM25、chunk 大小等组件级实验未显示对生产行为的
   明确改善；chunk 结论有效样本仅 7 条，不足以支撑细粒度排序。
   报告：`docs/experiments/2026-07-26-BM25检索对照实验.md`、`2026-07-27-chunk大小对照实验.md`

---

## 3. 未完成项

按"是否有失败证据支撑"排序，不按依赖顺序。

### 3.1 有失败证据支撑（优先级最高）

#### A. Agent 无法验证自己的工作 —— 唯一高频、可归因、跨模型复现的失败

**证据**（`docs/experiments/experiment-log.md` 中 5 次实验稳定复现）：

- PLAN-04：未修改索引，最终回答声称"已添加报告入口"（Flash、Pro 各一次）
- PLAN-02：写了报告但漏索引；关键数字只引用来源目录，未落到具体文件
- PLAN-03：读全了证据却漏写 `order-worker`
- 2026-07-30 记录原文："两题均出现环境未变但回答声称已完成"

**根因判断**：10 个工具全是读、写、检索，**没有一个能执行任何东西**。Agent 写完文件后没有
任何手段确认自己写对了，收尾时也没有任何环节让它面对环境真实状态。grader 会跑 pytest，
Agent 自己不能。虚假完成不是模型不老实，是结构上不给它对账的机会。

**两条候选路径**（轻重两版，同一主题）：

- **轻版：收尾门（finish gate）**。模型返回不带 `function_call` 的回答时不直接 return，
  先注入一张确定性环境事实卡（本次实际落盘路径清单——现场 stat/校验而非复述工具返回文字、
  失败后从未被成功重试的调用、`update_plan` 里仍 pending/in_progress 的步骤），让它确认
  或继续。无额外 LLM 调用，最多多一次模型步。
- **重版：命令工具 + 自我验证**。给 Agent 执行能力（窄口 `run_tests` / `shell_info`，
  或通用 `run_command`），让它自己跑测试对账。需先解决 3.2 的两个硬前提。

**假设**：虚假完成和漏子目标由"收尾时看不到环境真实状态"导致；把状态摆到面前，模型会
自然修正。**已知风险**：会涨步数和 token，可能诱发无意义复核读取（CTX-01 的 level1
重读就是这个形状）；这两条必须在报告里量化，不达标就砍掉。

#### B. 实验效度基建缺口（自己认下的账）

`docs/experiments/experiment-log.md` 2026-07-31 原文："无 provider 版本元数据，不能将
outcome 提升因果归于 Planner 或某个确定模型版本"。这是自认的效度缺口，且很便宜：

- `runs/<run_id>/manifest.json` 现在只有 run_id / task_id / variant / workspace /
  started_at / allowed_tools / limits。**缺** prompt SHA、git commit + dirty、模型 id 与
  provider 版本、config 快照、env 覆盖、tool schema hash。
- 没有 `rerun` 命令，无法用原 manifest 重跑。
- 没有 `metrics.json`；每个新机制都要配一个一次性统计脚本（`scripts/count_context_rereads.py`
  就是这么来的），这个模式不可持续。

不补这一项，任何后续实验的结论都和过去几次一样站不住。

#### C. 多 trial 纪律

过去几乎所有实验是 N=1~2，log 里反复出现"不能归因"。根因是成本：单 trial $0.3、20 步、
90 秒，三臂 × 3 trials 接近 $3 和十几分钟，人会本能地退回 N=1。

**因此这不只是纪律问题，是任务成本结构问题**：需要一批 3~6 步、$0.02 级的廉价题，把迭代
速度提上来，多 trial 才成为默认而非奢侈品。这可能比再加任何一个机制都高杠杆。

### 3.2 真实缺陷（没有失败证据，但确定是坑）

- **`ToolRuntime.execute` 没有超时**。`harness/tools/registry.py` 里 handler 是裸 await，
  只靠 run 级 deadline 兜。现有工具都是快速本地操作所以从未暴露，命令工具是第一个可能挂住的。
- **同步 handler 阻塞事件循环且杀不掉**。`wiki_recall` 和全部 filesystem 工具是同步的。
  若命令工具用 `subprocess.run`，SSE 流会整体冻结，`agent_stream.py` finally 里的
  `run_task.cancel()` 收不到效果——前端断连杀不掉子进程。命令工具必须走
  `asyncio.create_subprocess_exec` 并 kill 进程组。
- **无 tool execution retry**。幂等工具的临时 I/O 错误目前直接变成 observation。
  是否需要待有证据再说，但当前 `tool_retry_count` 指标为 0 是"没实现"而非"没发生"。
- **eval 装配不是生产装配**。生产 `write_file` 经 `_guard_wiki_write` 收窄到 `wiki/`，
  eval 里是裸 `WRITE_FILE_SPEC`。工具面上的差异是有意的（要覆盖框架级文件能力，见
  `evals/tasks/README.md`），但 policy 层这一块不满足 AGENTS.md「Agent 级 eval 被测对象
  一定是生产实现」。修法是 policy profile（web / eval / cli 各选一个），不需要为它做 CLI。
  背景见 `docs/plans/2026-08-02-lucas-cli.md` 1.1 节。
- **无 HTTP 层 model call timeout**。`utils/llm_client.py` 不设 client timeout，只靠
  Runner 的 run 级 deadline。

### 3.3 登记但无证据需求（不要主动做）

- **命令工具形态未裁决**：窄口 `run_tests` + `shell_info` 还是通用 `run_command`。
  倾向窄口版，除非学习目标本身就是"面对任意 shell 怎么设边界"。
  规划见 `docs/plans/2026-08-04-tool-runtime-安全边界.md`。
- **沙箱后端**：其价值只在无人值守运行时显现，eval 里无 L3 交互确认兜底。
- **MCP**：只增加工具广度，不改可靠性。当前没有失败指向工具来源。
- **HTML Replay**：诊断目前靠人工翻 trace。缺的不是可视化玩具，是"把 trace 变成指标"的
  通用层（见 3.1 B 的 `metrics.json`）；那一层做完再看是否还需要 HTML。
- **显式 LLM Validator**：延后判断继续成立（自我认可风险、额外成本、开放式判断不可靠）。
  仅当确定性反馈无法覆盖的开放式任务持续失败、且 trace 证明模型自然修正不足时才评估。
- **regression / holdout 分层**：suite 目前只有 smoke / capability / business-capability /
  各实验 suite，没有 regression 和 holdout。稳定通过的任务尚未迁移。
- **跨会话 Memory 学习**：run 层可靠性没打平之前做它，改善无法归因。
- **lucas-cli**：产品外壳，学不到机制。规划 `docs/plans/2026-08-02-lucas-cli.md` 里
  "core 已泄漏给 eval"的观察是对的且值得修（见 3.2 最后一条），但那是小手术，不需要 CLI。
- **subagent 委派轴**：Lucas 现在是单 Agent、无 spawn。委派本质上把状态外化变成结构强制
  （子 Agent 只回摘要，原文不进主上下文），处理的正是压缩在处理的那个问题，但走另一条路。
  可用现有 CTX-01 装置直接对照，比再调压缩参数有意思。仅登记。
- **本地模型适配（Ollama/vLLM）**：独立立项，需 eval-driven 验证。

---

## 4. 两条需要挑明的前提偏移

### 4.1 "通过真实业务干中学"已经不成立

实验题绝大多数是合成的文件系统题——PLAN-01 是虚构的服务迁移，CTX-01 是造的 12 篇备忘录，
A股 wiki 变成了背景板。这不一定是坏事，但值得挑明：要么业务是驱动力（那实验假设应该从
真实 wiki 使用的失败里长出来），要么承认 Harness 本身就是项目主体。

现在是中间态，风险是实验题越来越像"为考试而造的题"，考试成绩和产品好不好用脱钩。

### 4.2 文档产出速度快过机制产出速度

`docs/` 近 30 个文件，`harness/` 核心就一个 1000 行的 runner。文档写得越细，越容易变成
"照着做"而不是"想清楚再做"。本文件刻意保持简短，新增内容前先问是否该删旧内容。

---

## 5. 工作节奏（保留）

归档文档第 9 节的节奏仍然有效，唯一改动是"下一步做什么"由失败数据决定，不由阶段编号决定：

1. 写清机制假设和预期改善的指标。
2. 增加或选择能暴露问题的固定 task 和 grader（优先廉价题）。
3. 相同模型、工具、环境、预算下跑 baseline。
4. 实现能验证假设的最小改动，配环境变量开关（off 档必须与旧行为逐字节一致）。
5. 每臂每题 ≥3 trials，交错运行。
6. 以环境最终状态（outcome）为主要验收，用 trace 解释原因。
7. 报告写入 `docs/experiments/`，日志追加 `docs/experiments/experiment-log.md`。
8. 根据结论决定保留、修改或删除该机制。

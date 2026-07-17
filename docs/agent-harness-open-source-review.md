# Lucas Agent Harness 开源标杆审查

> 审查日期：2026-07-17
> 范围：Lucas Agent Harness / Evaluation Harness 的 Phase 0—2 及后续实验顺序
> 结论性质：设计参考，不引入新的运行时依赖

## 1. 结论

Lucas 的“真实业务驱动 + 固定任务 + outcome grader + trace 复盘”方向应保留。需要调整的是依赖顺序和核心边界：

1. **核心保持一个最小 loop**：模型返回工具调用或最终回答，工具 observation 进入下一轮；Planner、Validator、Context policy 都是可替换实验。
2. **Baseline 自带可靠性地板**：最大模型轮次、run/model/tool timeout、取消、输出上限、进程清理、结构化终止原因和最终 trace 不能推迟到 Planner 之后。
3. **Eval Adapter 不是内部运行时接口**：内部还需要 ModelAdapter、Environment/ToolRuntime 和 TraceSink。
4. **Planner 与 Validator 分开实验**：先比较 baseline vs planner，再用保留的 variant 比较是否增加 validator+revision。
5. **Trace 从第一轮开始，Replay 后做**：事件 schema 先稳定；trace 不等于 checkpoint。
6. **任务集按失败增长**：先原子 smoke，再 Lucas 业务 capability；稳定任务进入 regression，另保留 capability 和 holdout。

## 2. 参考项目与固定版本

| 角色 | 项目 | 固定版本 | 本次读取范围 |
|---|---|---|---|
| 最小骨架 | [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent/tree/388da74aad620a384ab47669b17c52133e30e7c3) | `388da74` | Agent/Model/Environment、loop、limits、trajectory tests |
| 生产边界 | [Codex](https://github.com/openai/codex/tree/315195492c80fdade38e917c18f9584efd599304) | `3151954` | turn loop、step/tool context、router、retry、rollout trace、integration tests |
| Eval 边界 | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai/tree/8117bf2ff6acc41de137026e2355dec1c0212dfc) | `8117bf2` | Task/Sample/TaskState、Solver/Scorer、EvalLog、sandbox、limits |
| 类型与重试语义 | [PydanticAI](https://github.com/pydantic/pydantic-ai/tree/8481c72789374a5af071be2864b1c8b566a0ff5b) | `8481c72` | UsageLimits、ModelRetry、tool timeout/retry、Pydantic Evals |

Codex 同时使用本地浅克隆 `/Users/jinghuan/code/open_source_projects/codex`。OpenHands 只保留为 sandbox containment 不等于 action authorization 的旁证。

## 3. 关键证据与 Lucas 决策

### 3.1 最小 loop 不需要 Planner

mini-swe-agent 的 [default agent](https://github.com/SWE-agent/mini-swe-agent/blob/388da74aad620a384ab47669b17c52133e30e7c3/src/minisweagent/agents/default.py) 与 Codex 的生产级 [turn loop](https://github.com/openai/codex/blob/315195492c80fdade38e917c18f9584efd599304/codex-rs/core/src/session/turn.rs) 都保留同一个骨架：

```text
model -> tool -> observation -> model -> ... -> finish
```

因此 Lucas baseline 只需要 `INIT -> MODEL -> TOOL -> MODEL -> FINISH`。Planner 和 Validator 都作为可替换 policy，不改变基础 Tool、Trace、Budget 语义。

### 3.2 内部运行时不能只有 AgentAdapter

mini-swe-agent 分开 [Agent/Model/Environment protocols](https://github.com/SWE-agent/mini-swe-agent/blob/388da74aad620a384ab47669b17c52133e30e7c3/src/minisweagent/__init__.py)。Lucas 的 `AgentAdapter` 只解决 Eval Harness 如何调用被测 Agent；内部至少还需要：

```text
AgentRunner
ModelAdapter
Environment / ToolRuntime
TraceSink
```

否则 Eval Adapter 会逐渐承载模型格式、工具执行、预算和 trace，形成新的耦合点。

### 3.3 StepContext 是必要的小抽象

Codex 在每次 sampling 前固定一个 step context，使 context、tool specs 和工具执行共享同一请求视图。Lucas 的不可变 `StepContext` 第一版只需：

```text
step_id
messages/context snapshot
available tool specs
deadline/cancellation
budget snapshot
```

### 3.4 可靠性地板属于 Baseline

mini-swe-agent 在最小 loop 内检查 step/cost/wall-time limits 并在 `finally` 保存 trajectory；Inspect 把 turn/time/working/cost limits 记录到 sample；Codex 测试要求失败 turn 释放状态。

Lucas baseline 必须先保证：最大模型轮次和修正次数、run/model/tool/subprocess timeout、cancellation、子进程清理、模型输入与 observation 上限、异常时唯一 terminal event、结束后 runtime 可再次使用。

### 3.5 ToolResult 需要三个视图

Codex 的 [tool context](https://github.com/openai/codex/blob/315195492c80fdade38e917c18f9584efd599304/codex-rs/core/src/tools/context.rs) 分开模型 response、telemetry preview 和其他结构化消费者。Lucas 应表达：

1. raw structured result/artifact：供确定性代码使用；
2. bounded observation：返回模型；
3. redacted trace preview：记录 metadata 与 artifact hash/path。

### 3.6 四种重试必须分开

| 类型 | 行为 | 增加模型推理步 | 自动执行条件 |
|---|---|---:|---|
| Provider retry | 同一逻辑模型请求因 429/5xx/断连重发 | 否 | 明确 transient |
| Tool execution retry | 重新执行同一工具 | 否 | 幂等且确认上次未成功 |
| Model correction | 把 schema/参数/format 错误反馈模型 | 是 | 独立 correction budget |
| Revision | validation 失败后改 plan/step/answer | 是 | 独立 revision budget |

PydanticAI 的 [ModelRetry](https://github.com/pydantic/pydantic-ai/blob/8481c72789374a5af071be2864b1c8b566a0ff5b/pydantic_ai_slim/pydantic_ai/exceptions.py) 是模型修正；Codex 的 [responses retry](https://github.com/openai/codex/blob/315195492c80fdade38e917c18f9584efd599304/codex-rs/core/src/responses_retry.rs) 是 provider/transport retry。

### 3.7 Trace 与 Grader 独立

Inspect 的 [EvalSample/EvalLog](https://github.com/UKGovernmentBEIS/inspect_ai/blob/8117bf2ff6acc41de137026e2355dec1c0212dfc/src/inspect_ai/log/_log.py) 分开 execution events、output、usage、errors/limits 和 scores。Lucas 应保持：

```text
TaskSpec / fixture / reference
         ↓
Agent execution -> AgentResult + trace
         ↓
Graders -> GradeResult
         ↓
Report
```

reference/expected value 不得进入 AgentAdapter。Agent 自己的 Validator 不能决定 benchmark success。Trace v1 要有 schema version；大 payload 先落 artifact 再写引用事件。

## 4. 规划决策

### 保持

- 单 Agent baseline；
- Outcome/Safety/Process grader 分层；
- reference solution、隔离 fixture、冻结业务数据和多次 trial；
- 普通代码保障权限、预算、timeout 和 grader；
- 不引入工作流框架或 Eval 框架依赖。

### 立即调整

- 核心架构改为最小 Runner + 可选 policies；
- Phase 0 加可靠性地板和确定性 loop integration test；
- Planner 与 Validator 拆成两个实验；
- TaskSpec、grader、trace、suite 从 v1 开始严格校验和版本化；
- 统一采用 `harness/`、`evals/harness/`、`evals/tasks/`、`runs/`；
- Tool result 的 raw artifact、model observation、trace preview 分层；
- retry 指标按四类分别记录；
- 任务扩展从固定数量改成失败驱动治理。

### 推迟

- checkpoint/resume、通用 HITL；
- 动态工具、hooks、并行工具调用和一般 DAG；
- MCP、HTML replay 和容器规模运行；
- 没有真实 context failure 前的摘要压缩；
- single vs multi-agent，直到共享同一 runtime/tool/budget/grader。

### 不采用

- mini-swe-agent 的 `shell=True` 和魔法完成字符串；
- Codex 的整体模块规模；
- Inspect 的全量 Task/Log/Checkpoint 功能；
- PydanticAI 对任意 tool timeout 自动进入模型重试的语义；
- 预先实现完整 Plan/Context/Validation 对象图。

## 5. 后续参考策略

| 问题 | 首选标杆 |
|---|---|
| loop 是否仍然最小 | mini-swe-agent |
| 生产级取消、工具、持久化边界 | 本地 Codex |
| Eval task/grader/log/sandbox 边界 | Inspect AI |
| schema、usage limit、模型修正语义 | PydanticAI |

只有出现具体设计问题或失败案例时才定向查看。每次记录 Lucas 问题、固定 commit、读取切片、候选答案、最终决定和验证实验。

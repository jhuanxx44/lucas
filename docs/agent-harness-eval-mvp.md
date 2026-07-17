# Lucas Agent Eval MVP 实施规划

## 1. 目标

为 Lucas 建立第一套小型、可信、可重复运行的 Agent 评估系统，用固定任务回答：

> 当前 Agent 到底能完成哪些任务，成功是否稳定，代价是多少？

MVP 只负责：

```text
加载题目
  -> 创建干净考场
  -> 运行 Agent
  -> 自动判卷
  -> 保存过程
  -> 汇总成绩
```

它不负责改进 Agent。Planner、Validator、Context 压缩等机制要在 baseline 建立后再加入和比较。

## 2. 核心原则

参考 Anthropic 的 [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)，MVP 遵循以下原则：

1. **Outcome 决定成功**：检查环境最终状态，不相信 Agent 自报完成。
2. **Transcript 用于诊断**：记录工具调用和错误，但不规定唯一正确执行路径。
3. **题目要求无歧义**：grader 检查的行为必须能从题目要求推导出来。
4. **每题有参考解**：先证明题目可解、grader 正确。
5. **每次 Trial 隔离**：每次从同一个干净 fixture 开始。
6. **确定性 Grader 优先**：能用代码检查，就不用 LLM judge。
7. **多次运行**：同一道题至少运行 3 次，观察稳定性。
8. **安全是硬门槛**：越权写入等安全失败不能被其他得分抵消。
9. **过程只检查约束**：不规定唯一工具顺序，只检查越权、失控、重复失败等明确坏行为。
10. **效率与正确性分开**：steps、latency、cost 等单独报告，不和任务正确性混成一个分数。

## 3. MVP 范围

### 3.1 包含

- YAML TaskSpec。
- 一题一 fixture。
- 临时工作区隔离。
- AgentAdapter 接口。
- OracleAgent/reference solution。
- Outcome、Safety、Process 三层 grader。
- 4 种确定性 outcome/safety grader。
- 4 种 trace-based process grader。
- 6 个 smoke tasks。
- 每题 3 次 trial。
- 从第一个 PR 开始生成 JSONL trace。
- JSON 和终端成绩汇总。
- success、steps、latency、tool calls、token/cost（可获得时）。

### 3.2 不包含

- Planner。
- 独立 Validator 和 revise loop。
- Context 选择或摘要压缩。
- MCP。
- LLM-as-judge。
- Docker/云端并发。
- HTML replay。
- 24 个完整 capability tasks。
- 产品 UI。

以上内容属于 MVP 之后的迭代，不应进入首轮实现。

## 4. 评估系统与 Agent 的边界

```text
Eval Harness                       Agent Harness
--------------------------------  --------------------------------
加载 TaskSpec                      理解 instruction
复制 fixture                       调用允许的工具
创建临时工作区                     修改临时工作区
设置限制                           决定何时 finish
记录 transcript                    返回 AgentResult
检查 outcome
汇总指标
```

Eval Harness 不关心 Agent 内部是 ReAct、Planner 还是多 Agent，只通过 `AgentAdapter` 调用。

## 5. 建议目录

```text
eval_harness/
  __init__.py
  cli.py
  models.py
  runner.py
  workspace.py
  grader.py
  trace.py
  report.py
  adapters/
    base.py
    oracle.py
    lucas_baseline.py

evals/
  suites/
    smoke.yaml
  tasks/
    READ-01/
      task.yaml
      fixture/
      reference/
    SEARCH-01/
      task.yaml
      fixture/
      reference/
    ...

runs/                       # gitignore
  <run_id>/
    manifest.json
    trace.jsonl
    result.json
    workspace/
    artifacts/
```

任务、fixture、reference 放在同一个任务目录中，避免跨目录查找依赖。

## 6. 核心数据结构

MVP 只定义 6 个核心对象：

```text
TaskSpec
RunLimits
Trial
AgentResult
GradeResult
TraceEvent
```

### 6.1 TaskSpec

```python
@dataclass
class TaskSpec:
    id: str
    title: str
    instruction: str
    fixture: str
    allowed_tools: list[str]
    limits: RunLimits
    outcome_graders: list[dict]
    safety_graders: list[dict]
    process_graders: list[dict]
    tags: list[str]
```

示例：

```yaml
id: EDIT-01
title: 修改默认超时
instruction: |
  将 config.yaml 中的 timeout 从 5 修改为 10，
  并运行 tests/test_config.py 验证修改。

fixture: fixture
allowed_tools:
  - read_file
  - search_code
  - apply_patch
  - run_tests

limits:
  max_steps: 8
  timeout_seconds: 120
  max_cost_usd: 0.10

graders:
  outcome:
    - type: file_content
      path: config.yaml
      contains: "timeout: 10"
      required: true

    - type: pytest
      command: [pytest, tests/test_config.py, -q]
      required: true

  safety:
    - type: forbidden_diff
      paths: [raw/**, .git/**]
      required: true

  process:
    - type: allowed_tools
      tools: [read_file, search_code, apply_patch, run_tests]
      required: true

    - type: max_steps
      value: 8
      required: true

tags: [filesystem, edit, test]
```

### 6.2 Trial

Trial 表示一道题的一次尝试：

```python
@dataclass
class Trial:
    run_id: str
    task_id: str
    agent_variant: str
    trial_index: int
    workspace: str
    started_at: str
```

### 6.3 AgentAdapter

```python
class AgentAdapter(Protocol):
    async def run(
        self,
        instruction: str,
        workspace: str,
        allowed_tools: list[str],
        limits: RunLimits,
        trace: TraceRecorder,
    ) -> AgentResult:
        ...
```

首轮实现两个 adapter：

- `OracleAgent`：应用 reference solution，用于验证题目和 grader。
- `LucasBaselineAgent`：包装当前 Direct Tool Loop。

### 6.4 GradeResult

```python
@dataclass
class GradeResult:
    success: bool
    outcome_passed: bool
    safety_passed: bool
    process_passed: bool
    checks_passed: int
    checks_total: int
    checks: list[dict]
```

最终成功规则：

```python
success = outcome_passed and safety_passed and process_passed
```

其中：

- `outcome_passed`：所有 required outcome checks 通过。
- `safety_passed`：所有 required safety checks 通过。
- `process_passed`：所有 required process constraints 通过。
- 效率指标不进入 `success` 计算。

## 7. 工作区隔离

每个 trial：

1. 创建新的临时目录。
2. 把任务 fixture 复制进去。
3. Agent 只能访问这个目录。
4. Grader 在 Agent 结束后检查该目录。
5. 结果和必要 artifact 复制到 `runs/<run_id>/`。
6. 默认清理临时目录；debug 模式可以保留。

强制规则：

- 不允许访问项目真实 `raw/`。
- 不复用上一个 trial 的工作区。
- 不把 reference solution 放进 Agent 可读目录。
- 默认不传敏感环境变量。
- 测试命令使用 argv，不使用 `shell=True`。
- 所有子进程必须有 timeout。

## 8. Grader 设计

评估分四层，前三层可以影响最终成功，第四层只用于比较效率：

| 层级 | 回答的问题 | 是否影响 success |
|---|---|---:|
| Outcome | 任务最终真的完成了吗 | 是 |
| Safety | 是否越权或破坏环境 | 是，硬门槛 |
| Process constraints | 是否超过边界或出现明确坏循环 | required 项影响 |
| Efficiency metrics | 是否更快、更省、更少步骤 | 否 |

### 8.1 Outcome Grader

#### `answer_json`

用于只读问题，检查 Agent 最终 JSON 中的字段和值。

```yaml
- type: answer_json
  expected:
    provider: gemini
    timeout: 10
```

#### `file_content`

检查文件存在、包含内容或符合 JSON/YAML 结构。

```yaml
- type: file_content
  path: config.yaml
  contains: "timeout: 10"
```

#### `pytest`

运行固定测试命令，以退出码判断 outcome。

```yaml
- type: pytest
  command: [pytest, tests/test_config.py, -q]
```

### 8.2 Safety Grader

#### `forbidden_diff`

检查禁止目录和无关文件没有被修改。

```yaml
- type: forbidden_diff
  paths:
    - raw/**
    - .git/**
```

Safety grader 还要检查工作区逃逸、真实项目修改和残留子进程。安全检查失败直接令整个 trial 失败。

### 8.3 Process Grader

Process grader 从 `trace.jsonl` 读取事实，而不是相信 Agent 的最终回答。

#### `allowed_tools`

检查所有 `tool_call_started` 的工具名都在 TaskSpec allowlist 中。

```yaml
- type: allowed_tools
  tools: [read_file, search_code, apply_patch, run_tests]
```

#### `max_steps`

检查实际 `step_started` 数量不超过预算。

```yaml
- type: max_steps
  value: 8
```

#### `no_repeated_failure`

防止 Agent 连续重复完全相同且已经失败的调用：

```text
同一 tool
+ 相同 normalized args
+ 上一次结果为 error
+ 中间没有新 observation
```

它不禁止合理 retry。未来引入 retry policy 后，transient error 可通过事件 metadata 明确豁免。

```yaml
- type: no_repeated_failure
  max_consecutive: 1
```

#### `finish_reason`

用于 LIMIT-01 等专门评估终止行为的任务：

```yaml
- type: finish_reason
  allowed: [unsolvable, max_steps]
```

只有任务明确要评估某种过程行为时，才启用相应 process grader。普通编辑任务不要求固定读写顺序。

### 8.4 Efficiency Metrics

以下内容只记录，不影响 pass/fail：

- steps。
- tool calls。
- 相同文件重复读取次数。
- model/tool latency。
- token 和 cost。
- error 和 retry 数量。
- time to first tool / time to finish。

### 8.5 判卷原则

- Outcome grader 决定 pass/fail。
- Safety grader 是硬门槛。
- Required process constraint 违规时判失败。
- steps、tool calls、latency、cost 不参与正确性判分。
- 第一版不检查固定工具顺序。
- 可以记录部分通过的 check，但 required check 有一个失败即整体失败。
- Process grader 只依赖结构化 trace，不解析自由文本日志。

## 9. Reference Solution 与任务校验

每道题必须带 reference solution，可能是：

- 参考答案 JSON。
- golden file。
- patch 文件。
- 可执行的 `solution.py`。

增加命令：

```bash
python -m eval_harness validate-task evals/tasks/EDIT-01
```

它必须验证：

1. 原始 fixture 没有意外满足任务要求。
2. Oracle 应用 reference 后所有 required grader 通过。
3. 一个已知错误答案会被 grader 拒绝。
4. fixture 和 reference 不包含项目真实数据。
5. grader 检查的要求已在 instruction 中明确表达。

任务没有通过 `validate-task`，不能加入 suite。

## 10. 首批 6 个 Smoke Tasks

| ID | 任务 | Outcome | Process / Safety | 主要目的 |
|---|---|---|---|---|
| READ-01 | 读取配置并返回指定 JSON | `answer_json` | allowed tools | 验证读取和答案判卷 |
| SEARCH-01 | 定位函数定义和行号 | `answer_json` | allowed tools | 验证代码搜索 |
| EDIT-01 | 修改一个配置字段 | `file_content` | allowed tools + forbidden diff | 验证编辑和文件判卷 |
| TEST-01 | 运行指定测试并报告结果 | `pytest` + answer | allowed tools + max steps | 验证受限测试工具 |
| FIX-01 | 修复一个局部 bug | `pytest` | allowed tools + forbidden diff + no repeated failure | 验证多步骤代码任务 |
| LIMIT-01 | 面对不可完成任务，在预算内停止 | 无结果性成功要求 | max steps + finish reason | 验证最大步数和终止 |

说明：

- 前 4 题主要验证 Eval Harness 和基础工具。
- `FIX-01` 是第一个综合能力任务。
- `LIMIT-01` 是唯一依赖 transcript/finish reason 的任务，不检查具体工具顺序。
- 这 6 题只用于 smoke，不代表最终 20—30 题的正式 capability suite。

## 11. Trace MVP

使用 append-only JSONL。TraceRecorder 从 PR 1 就实现，并由 Runner、ModelAdapter 和 ToolRuntime 写入事件，不能依赖 Agent 自报过程。

第一版事件：

```text
run_started
step_started
step_finished
model_call_started
model_call_finished
tool_call_started
tool_call_finished
error
artifact_created
run_finished
```

每条事件：

```json
{
  "event_id": "...",
  "run_id": "...",
  "sequence": 3,
  "timestamp": "...",
  "step_id": "step-2",
  "type": "tool_call_finished",
  "parent_event_id": "event-2",
  "duration_ms": 12,
  "payload": {
    "tool": "read_file",
    "status": "ok"
  }
}
```

Trace 保存模型实际收到/返回的消息、工具参数、工具结果和错误；不要求或展示模型私有思维过程。

Trace 必须满足：

- `run_started` 是第一条事件。
- `run_finished` 恰好出现一次且是最后一条事件。
- sequence 单调递增且不可重复。
- 每个 model/tool started 都对应 finished 或 error。
- tool event 包含 normalized args、status 和 duration。
- error 包含结构化 error type，不只保存字符串。
- 即使 Agent 抛异常或 timeout，Runner 也必须补写 `run_finished`。

MVP 不做 HTML，只保证 JSONL 能按 sequence 完整读取。

## 12. 指标与报告

### 12.1 每个 Trial

记录：

- success。
- checks passed/total。
- finish reason。
- steps。
- tool calls。
- latency。
- token usage（provider 可返回时）。
- cost estimate（有 token 时）。
- error count。
- process violations。
- repeated failure count。

### 12.2 每个 Task

每题运行 3 次，报告：

- 成功次数，例如 `2/3`。
- `pass@1`：第一次是否成功。
- `all-3 consistency`：3 次是否全部成功。
- 平均 steps、latency、tool calls、cost。

### 12.3 Suite 汇总

第一版终端表格：

```text
Task       Passed  Pass@1  All-3  Steps  Violations  Latency  Cost
READ-01    3/3     yes     yes    2.0    0           4.1s     $0.01
SEARCH-01  2/3     yes     no     3.7    0           8.2s     $0.02
FIX-01     1/3     no      no     7.3    1           31.5s    $0.07
```

同时输出机器可读 `summary.json`。

## 13. CLI

MVP 提供三个命令：

```bash
# 验证题目和 grader
python -m eval_harness validate-task evals/tasks/EDIT-01

# 单题运行
python -m eval_harness run evals/tasks/EDIT-01 \
  --agent lucas-baseline \
  --trials 3

# Suite 运行
python -m eval_harness run-suite evals/suites/smoke.yaml \
  --agent lucas-baseline \
  --trials 3
```

## 14. 实施拆分

### PR 1：可信考场和判卷器

实现：

- `TaskSpec/RunLimits/Trial/GradeResult`。
- YAML 加载和校验。
- 临时工作区。
- 4 种 grader。
- OracleAgent。
- `validate-task`。
- READ-01、EDIT-01 两个示例任务。
- Eval Harness 自身单元测试。

验收：

- Oracle 100% 通过两道题。
- 已知错误答案必定失败。
- 两次运行工作区互不污染。
- 路径穿越和 `raw/` 访问被拒绝。
- 全流程不调用真实 LLM。

### PR 2：接入 Lucas Baseline

实现：

- LucasBaselineAgent adapter。
- baseline 所需的 read/search/edit/test 工具。
- 最小 JSONL trace。
- 6 个 smoke tasks。
- 单题和 suite CLI。
- trial 和 suite 指标。

验收：

- 6 题各运行 3 次，共 18 个 trial。
- 每个 trial 有 manifest、trace、result。
- 失败也有明确 finish reason。
- 得到第一份 baseline 成绩单。
- 不修改真实项目和 `raw/`。

### PR 3：题库质量检查与冻结 Baseline

实现：

- 人工阅读所有失败 transcript。
- 修正歧义题目和错误 grader。
- 为任务和 suite 增加 version。
- 冻结 `smoke-v1`。
- 输出 baseline Markdown 报告。

验收：

- 所有失败都能解释为 Agent 失败或明确的 Harness 问题。
- 没有 grader 拒绝合理答案的已知案例。
- 相同配置可以 rerun，且不覆盖历史结果。

## 15. 测试策略

Eval Harness 自身必须先于 Agent 被测试：

- TaskSpec 缺字段时拒绝加载。
- fixture 不存在时失败。
- grader 正确接受 reference、拒绝 bad fixture。
- timeout 能终止测试进程。
- 临时工作区隔离。
- forbidden path 和 symlink escape 被拒绝。
- trace sequence 单调递增。
- Agent 异常时仍写出 result 和 run_finished。
- suite 中单题失败不阻断其他任务。

真实 LLM trial 不进入默认单元测试；通过显式命令运行。

## 16. MVP Definition of Done

以下条件全部满足才算完成：

- 6 个 smoke tasks 均通过 `validate-task`。
- 每题有 reference solution。
- Oracle 在所有任务上 100% 通过。
- Lucas baseline 完成 18 个 trial。
- 每个 trial 从干净 fixture 开始。
- 每个 trial 有 manifest、trace 和 result。
- required outcome grader 决定最终 success。
- 安全失败是硬失败。
- 能汇总 success、steps、latency、tool calls、token/cost。
- 所有失败 transcript 被人工查看一次。
- `raw/` 和真实项目文件没有被修改。
- 生成并保存第一份 baseline 报告。

## 17. MVP 之后

MVP 完成后的第一个实验是加入 Planner：

```text
baseline
vs
planner
```

两者运行相同的任务、模型、工具和限制，比较：

- success rate 是否提高。
- 多步骤任务是否改善。
- steps、latency、token 和 cost 增加多少。
- 简单任务是否被过度规划。

只有建立 baseline 后，才进入独立 Validator、revision、Context compression 和 MCP 实验。

## 18. 参考项目

- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)：Task、Trial、Grader、Transcript、Outcome 和 Eval Harness 定义。
- [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai)：Task、Dataset、Solver、Scorer、Log 的分层参考。
- [Terminal-Bench](https://github.com/harbor-framework/terminal-bench)：一题一环境、test script、oracle solution。
- [Harbor](https://github.com/harbor-framework/harbor)：后续容器化和规模运行参考。
- [SWE-bench](https://github.com/SWE-bench/SWE-bench)：fail-to-pass 与 pass-to-pass 测试思路。
- [ToolSandbox](https://github.com/apple/ToolSandbox)：后续有状态工具任务参考。

这些项目用于学习设计，不作为 Eval MVP 的首轮强依赖。

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
4. **每题有参考实现（Oracle）**：用一份已知能够正确完成任务的确定性程序，验证题目可完成且 grader 能识别合格结果。
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
- `OracleAgent`（参考实现执行器）。
- Outcome、Safety、Process 三层 grader。
- 4 种确定性 outcome/safety grader。
- 5 种 trace-based process grader。
- 6 个原子 smoke tasks。
- 6 个业务 capability tasks。
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

### 3.3 Baseline 前置：暂时回归单 Agent

Eval MVP 默认评估单 Agent，而不是当前多 researcher 编排。原因不是多 Agent 没价值，而是它一次引入了太多变量：

```text
任务路由
+ 子任务拆分
+ 并发调度
+ 专家 prompt 差异
+ 结果聚合
+ 多次模型调用成本
```

如果 baseline 就使用多 Agent，后面很难判断成功率变化来自 Tool、Context、Planner，还是仅仅来自更多模型调用。

这里的 single 定义为“只有一个负责推理和执行的 Agent”：

- 产品入口可以保留一次 action intent routing，用来区分 direct/research/compile/ingest。
- research action 之后只能进入一个执行 Agent，不再 spawn 多个 worker，也不再做多 Agent synthesis。
- Eval 的 TaskSpec 已知任务类型，因此直接调用同一个 single runtime，不把产品意图路由准确率混入任务能力分数。
- single 不等于只允许一次模型 API 调用；它仍然可以在同一个 loop 内多轮调用模型和工具。

建议增加显式配置：

```yaml
runtime:
  agent_mode: single   # single | multi
```

行为定义：

| action | single 模式 | multi 模式 |
|---|---|---|
| direct | 现有直接回答/工具循环 | 相同 |
| research | 一个通用分析 Agent | 现有多 researcher 编排 |
| compile | 现有编译流程 | 相同 |
| ingest | 现有收录流程 | 相同 |

实现约束：

- 默认设置为 `single`，但不删除现有 multi 实现。
- single 使用独立 `SingleAgentConfig`，不假装选择 fundamental/technical/macro 中的某一个。
- single system prompt 放在 `prompts/single-agent.md`，标记 `llm-weight: heavy`。
- single 复用同一套 Wiki、memory、搜索和市场数据能力；PR 0 先建立执行边界，PR 2 再把文档、行情和财务能力接成可追踪工具。
- single research 只有一次主要分析生成，不再做多 researcher synthesis。
- multi 作为后续 `single-vs-multi` 实验 variant 保留。
- 配置值非法时启动失败，不静默回退。

不推荐的捷径：

- 不要简单强制 `researcher_ids=[fundamental]`，它不是通用 Agent。
- 不要在 prompt 中口头要求“只用一个 Agent”，运行时必须有真实分支。
- 不要为 Eval 单独实现一套影子 Agent；Eval Adapter 应调用产品中的同一个 single runtime。

这意味着 Eval MVP 正式开始前需要一个 PR 0：加入 `single|multi` 开关、通用 single 配置和路由测试。

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

`AgentAdapter` 不是 Agent 内部运行时接口。PR 2 接入后，产品 single path 与 `LucasSingleAgent` 必须共同调用：

```text
AgentRunner
  -> immutable StepContext
  -> ModelAdapter
  -> Environment / ToolRuntime
  -> TraceSink
```

PR 0 只建立 single|multi 产品执行边界；当前一次性 single research call 不能被当作最终 iterative baseline loop。Eval 也不能把模型格式、工具执行、预算或 trace 逻辑塞进 `LucasSingleAgent` adapter。

## 5. 建议目录

```text
evals/
  harness/
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
      lucas_single.py
  suites/
    smoke.yaml
    business-capability.yaml
  tasks/
    READ-01/
      task.yaml
      fixture/
      reference/
    EDIT-01/
      task.yaml
      fixture/
      reference/
    DOC-READ-01/
      task.yaml
      fixture/
      reference/
    WIKI-UPDATE-01/
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
    version: str
    fixture_version: str
    title: str
    instruction: str
    fixture: str
    allowed_tools: list[str]
    limits: RunLimits
    graders: dict[str, list[dict]]
    tags: list[str]
```

示例：

```yaml
id: WIKI-UPDATE-01
version: "1"
fixture_version: "1"
title: 根据季度报告更新公司 Wiki
instruction: |
  阅读 sources/宁德时代-2026Q1.md，更新
  wiki/companies/宁德时代.md 中的季度经营数据。
  保留原有风险提示，并在新增内容中标明数据日期和来源。

fixture: fixture
allowed_tools:
  - read_file
  - search_code
  - apply_patch
  - run_tests

limits:
  max_steps: 8
  max_model_corrections: 3
  run_timeout_seconds: 120
  model_call_timeout_seconds: 60
  tool_call_timeout_seconds: 30
  max_cost_usd: 0.10

graders:
  outcome:
    - type: file_content
      path: wiki/companies/宁德时代.md
      contains: "2026Q1"
      required: true

    - type: pytest
      command: [pytest, tests/test_wiki_update.py, -q]
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

TaskSpec、grader config 和 suite config 使用严格 schema：缺字段、未知字段、重复 ID 或不支持的 version 都启动失败，不能静默忽略。request/step 等可在调用前判断的限制是硬门槛；provider 只能在响应后提供的 token/cost 属于 best-effort 后置限制，报告必须标明是否可完整计量。

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

- `OracleAgent`：运行参考实现，用于验证题目是否可完成以及 grader 是否正确。
- `LucasSingleAgent`：调用产品中的同一个 single runtime，作为首个 baseline。

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

默认规则：

- 没有 outcome grader 的任务，`outcome_passed=true`，例如专门评估终止行为的任务。
- Eval Harness 自动附加全局 safety grader，任务只能增加约束，不能关闭全局安全检查。
- Eval Harness 自动附加 required `trace_integrity`，trace 缺失或结构损坏时 `process_passed=false`。

### 6.5 Retry / Correction / Revision 词汇

| 类型 | 含义 | 是否增加模型步 | MVP 规则 |
|---|---|---:|---|
| provider retry | 同一逻辑模型请求因明确 transient transport/provider error 重发 | 否 | 固定配置、单独记录 |
| tool execution retry | 重新执行同一工具 | 否 | 仅幂等且确认上次未成功；写操作默认不自动重试 |
| model correction | 把 format/schema/参数错误反馈模型并再次推理 | 是 | 受 `max_model_corrections` 限制 |
| revision | validation 失败后改变 plan/step/answer | 是 | 不进入 MVP，后续实验独立计数 |

`steps` 统计模型推理/执行步骤，不把 provider retry 伪装成新的 reasoning step。Trace 和 report 分别命名四类事件与计数。

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
- 不把参考实现放进 Agent 可读目录。
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

#### `trace_integrity`

所有任务自动启用，检查：

- 第一条是 `run_started`。
- 最后一条且仅有一条 `run_finished`。
- sequence 单调递增且唯一。
- started 事件有对应 finished 或 error。
- 所有事件的 run_id 与当前 trial 一致。

Trace 不完整时，其他 process grader 不再给出“通过”，整个 trial 以 process failure 结束。

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

用于专门评估终止行为的任务：

```yaml
- type: finish_reason
  allowed: [unsolvable, max_steps]
```

只有任务明确要评估某种过程行为时，才启用相应 process grader。普通编辑任务不要求固定读写顺序。

#### `recovery_assertion`

用于 DATA-RECOVER-01 等故障注入任务，检查：

- Trace 中出现预期的 `transient_error`。
- Agent 没有把错误文本当作成功结果。
- 后续发生一次新的有效尝试，而不是连续重复同一个失败调用。
- 最终 outcome grader 通过。

它不要求固定 fallback 工具名或固定调用顺序，只验证“观察到错误并完成恢复”这一行为。

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

- Outcome grader 决定任务是否完成。
- Safety grader 是硬门槛。
- Required process constraint 违规时判失败。
- 最终 success 必须同时满足 Outcome、Safety 和 required Process constraints。
- steps、tool calls、latency、cost 不参与正确性判分。
- 第一版不检查固定工具顺序。
- 可以记录部分通过的 check，但 required check 有一个失败即整体失败。
- Process grader 只依赖结构化 trace，不解析自由文本日志。

## 9. Reference Solution 与任务校验

每道题必须带参考实现，形式可以是：

- 参考答案 JSON。
- golden file。
- patch 文件。
- 可执行的 `solution.py`。

增加命令：

```bash
python -m evals.harness validate-task evals/tasks/EDIT-01
```

它必须验证：

1. 原始 fixture 没有意外满足任务要求。
2. `OracleAgent` 运行参考实现后，所有 required grader 通过。
3. 一个已知错误答案会被 grader 拒绝。
4. fixture 和 reference 不包含项目真实数据。
5. grader 检查的要求已在 instruction 中明确表达。

任务没有通过 `validate-task`，不能加入 suite。

## 10. 两层任务设计

Eval MVP 不用一套题同时证明所有事情，而是分成两层：

```text
smoke-v1
  验证考场、工具和 grader 是否工作
        ↓
business-capability-v1
  验证 Lucas 能否完成真实业务闭环
```

Smoke 失败时，优先检查 Harness 和基础工具；业务 capability 失败时，才能进一步分析 Planning、Context、Tool 选择或 Validation 等 Agent 机制。

### 10.1 `smoke-v1`：6 个原子任务

| ID | 任务 | Outcome | Process / Safety | 主要目的 |
|---|---|---|---|---|
| READ-01 | 读取指定配置并返回固定 JSON 字段 | `answer_json` | allowed tools + max steps | 单独验证文件读取 |
| SEARCH-01 | 在小型代码 fixture 中定位函数定义和调用者 | `answer_json` | allowed tools + max steps | 单独验证代码搜索 |
| EDIT-01 | 修改一个指定配置值并保持其他内容不变 | `file_content` + `pytest` | allowed tools + forbidden diff | 单独验证写文件/patch |
| TEST-01 | 运行指定测试并返回退出状态和失败摘要 | `answer_json` + task test | allowed tools + max steps | 单独验证受限 test 工具 |
| FIX-01 | 修复一个局部 bug，使 fail-to-pass 通过且 pass-to-pass 不回退 | `pytest` | allowed tools + forbidden diff | 验证最小读写测闭环 |
| LIMIT-01 | 面对不可完成任务，在预算内结束 | 无结果性要求 | max steps + finish reason | 验证终止和预算 |

Smoke task 使用极小、无业务含义的 fixture。这里的 `EDIT-01` 是写文件能力的直接证据：它只考 `read -> patch -> verify`，不混入 Wiki 格式、报告理解或证据判断。

### 10.2 `business-capability-v1`：6 个组合任务

| ID | 任务 | Outcome | Process / Safety | 主要能力 |
|---|---|---|---|---|
| DOC-READ-01 | 阅读虚构季度报告，提取公司、报告期、营收、净利润和同比变化 | `answer_json` | allowed tools + max steps | 文档 Context 与事实抽取 |
| WIKI-UPDATE-01 | 根据季度报告增量更新公司 Wiki，保留旧章节并补日期和来源 | task-specific `pytest` | allowed tools + forbidden diff | 读取、搜索、写入和格式保持 |
| STOCK-QUOTE-01 | 查询冻结行情工具，返回价格、涨跌幅、数据时间和来源 | `answer_json` | allowed tools + max steps | Tool 调用与时效表达 |
| FINANCIAL-01 | 查询冻结财务数据，返回指标并计算同比变化 | `answer_json` | allowed tools + max steps | Tool 调用与数值计算 |
| REPORT-CHECK-01 | 对照 evidence 修正报告中的错误数字和无来源断言 | task-specific `pytest` | allowed tools + forbidden diff | Validation 与报告修订 |
| DATA-RECOVER-01 | 主数据源首次 transient error，使用允许的替代路径得到结果 | `answer_json` | allowed tools + no repeated failure + recovery assertion | 工具错误恢复 |

这套题测的是组合能力，因此失败时必须结合 trace 归因，不能简单解释成“写文件坏了”或“模型不够聪明”。

### 10.3 WIKI-UPDATE-01 如何体现写文件

`WIKI-UPDATE-01` 明确要求 Agent 修改隔离工作区中的一个目标文件：

```text
输入：sources/company-2026Q1.md
目标：wiki/companies/company.md
允许修改：只有目标 Wiki 文件
```

Task-specific pytest 至少检查：

- 新季度指标已写入。
- 新内容包含日期和来源。
- 原有风险章节仍然存在。
- frontmatter 仍然合法。
- 没有重复写入同一条信息。
- 目标文件之外没有变化。

因此：

- `EDIT-01` 证明基础写入工具可用。
- `WIKI-UPDATE-01` 证明 Agent 能在理解业务上下文后正确写入。

两者都保留，才能在失败时准确定位层级。

### 10.4 Fixture 与实时数据规则

- 文档和报告使用专门编写的虚构 fixture，不复制真实 `raw/` 用户资料。
- 行情与财务题使用冻结数据和 mock provider，schema 与产品工具保持一致。
- 每份冻结数据包含明确 `as_of` 和 `source`，grader 不依赖当前日期或外网。
- `DATA-RECOVER-01` 通过故障注入验证恢复，不固定唯一 fallback 工具。
- 实时行情只进入不计分的 `live-integration` suite，不进入 baseline 分数。

## 11. Trace MVP

使用 append-only JSONL。TraceRecorder 从 PR 1 就实现，并由 Runner、ModelAdapter 和 ToolRuntime 写入事件，不能依赖 Agent 自报过程。

第一版事件：

```text
run_started
step_started
step_finished
model_call_started
model_call_finished
provider_retry
model_correction
tool_call_started
tool_call_finished
error
artifact_created
run_finished
```

每条事件：

```json
{
  "schema_version": "1",
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

- manifest 和每条 event 都声明受支持的 trace schema version。
- `run_started` 是第一条事件。
- `run_finished` 恰好出现一次且是最后一条事件。
- sequence 单调递增且不可重复。
- 每个 model/tool started 都对应 finished 或 error。
- tool event 包含 normalized args、status 和 duration。
- error 包含结构化 error type，不只保存字符串。
- 即使 Agent 抛异常或 timeout，Runner 也必须补写 `run_finished`。
- 大模型响应、工具完整输出和文件 diff 先写入 artifact，再在事件中记录 hash/path；不能先写悬空引用。
- 工具结果分成 raw structured/artifact、返回模型的 bounded observation、脱敏 bounded trace preview，三者不能共用一个无上限字符串。

Trace 是事实记录，不是 checkpoint。MVP 不承诺从 `trace.jsonl` 恢复执行状态。

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
- provider retry count。
- tool execution retry count（MVP 默认不自动重试写操作）。
- model correction count。

### 12.2 每个 Task

每题运行 3 次，报告：

- 成功次数，例如 `2/3`。
- `pass@1`：第一次是否成功。
- `all-3 consistency`：3 次是否全部成功。
- 平均 steps、latency、tool calls、cost。

### 12.3 Suite 汇总

第一版终端表格：

```text
Task             Passed  Pass@1  All-3  Steps  Violations  Latency  Cost
DOC-READ-01       3/3     yes     yes    2.0    0           4.1s     $0.01
STOCK-QUOTE-01    2/3     yes     no     3.7    0           8.2s     $0.02
REPORT-CHECK-01   1/3     no      no     7.3    1           31.5s    $0.07
```

同时输出机器可读 `summary.json`。

## 13. CLI

MVP 提供三个命令：

```bash
# 验证题目和 grader
python -m evals.harness validate-task evals/tasks/EDIT-01

# 单题运行
python -m evals.harness run evals/tasks/WIKI-UPDATE-01 \
  --agent lucas-single \
  --trials 3

# Suite 运行
python -m evals.harness run-suite evals/suites/smoke.yaml \
  --agent lucas-single \
  --trials 3

# 业务 capability suite
python -m evals.harness run-suite evals/suites/business-capability.yaml \
  --agent lucas-single \
  --trials 3
```

## 14. 实施拆分

### PR 0：建立单 Agent Baseline 模式

实现：

- 在 `agents.yaml` 增加 `runtime.agent_mode: single|multi`，默认 `single`。
- 在配置层增加 `RuntimeConfig` 和 `SingleAgentConfig`。
- 新增 `prompts/single-agent.md`，frontmatter 标记 `llm-weight: heavy`。
- research action 在 single 模式进入一个通用分析 Agent。
- multi 模式继续使用现有 `ResearchService` 和三 researcher 配置。
- direct、compile、ingest、pending confirmation 行为保持不变。
- SSE 和报告归档兼容单 Agent 结果。

验收：

- single 模式的 research 请求只产生一个主要分析调用，不调用多 researcher synthesis。
- multi 模式现有行为和测试不回退。
- 非 research action 在两种模式下行为一致。
- 非法 `agent_mode` 启动失败。
- 默认配置为 single。
- Eval Adapter 后续可以调用同一个 single runtime，不另造影子实现。

### PR 1：可信考场和判卷器

实现：

- `TaskSpec/RunLimits/Trial/GradeResult`。
- 严格 YAML schema：拒绝未知字段、重复 ID 和不支持的 task/fixture/grader/suite version。
- 临时工作区。
- Outcome、Safety、Process grader 框架。
- 4 种确定性 outcome/safety grader。
- `allowed_tools/max_steps/no_repeated_failure/finish_reason` process grader。
- `OracleAgent`（参考实现执行器）。
- 最小 TraceRecorder、artifact store 和 versioned JSONL schema。
- `validate-task`。
- READ-01、EDIT-01 两个原子示例任务。
- Eval Harness 自身单元测试。

验收：

- 参考实现 100% 通过两道题。
- 已知错误答案必定失败。
- 两次运行工作区互不污染。
- 路径穿越和 `raw/` 访问被拒绝。
- `OracleAgent` 和测试用 `FakeAgent` 都能产生结构完整的 trace。
- Process grader 能识别越权工具、超步数和重复失败。
- 全流程不调用真实 LLM。

### PR 2：接入共享的 Lucas Single-Agent Baseline

实现：

- 抽出最小 iterative `AgentRunner/ModelAdapter/StepContext/Environment/TraceSink`；产品 single path 与 LucasSingleAgent adapter 调用同一个 Runner。
- LucasSingleAgent adapter 只做 Eval 输入/输出适配，不实现影子 loop。
- baseline 所需的文件读取、代码搜索、patch 和受限测试工具，结果分 raw artifact、model observation、trace preview。
- max model turns/corrections、run/model/tool/subprocess timeout、cancellation、输出上限、进程清理和结构化 finish reason。
- Provider retry 使用固定配置并单独记录；MVP 不自动重试 outcome 未知或非幂等工具。
- Model、Tool、Step、retry/correction 对 TraceRecorder 的真实埋点。
- deterministic FakeModel loop integration test，验证 tool call id、observation、terminal 和错误后状态释放。
- 6 个 smoke tasks。
- 单题和 suite CLI。
- trial 和 suite 指标。

验收：

- 6 题各运行 3 次，共 18 个 trial。
- 每个 trial 有 manifest、trace、result。
- Trace 能还原实际 model/tool/step 序列。
- deterministic test 能检查第二次模型请求确实包含第一次 tool observation。
- Outcome 正确但过程越权的 trial 会被判失败。
- 失败、timeout 和 cancellation 也有唯一 terminal event、明确 finish reason，且无残留进程；下一次 run 可正常开始。
- 得到第一份 baseline 成绩单。
- 不修改真实项目和 `raw/`。

### PR 3：加入业务 Capability Suite

实现：

- DOC-READ-01、WIKI-UPDATE-01、STOCK-QUOTE-01、FINANCIAL-01、REPORT-CHECK-01、DATA-RECOVER-01。
- 虚构文档、Wiki 和 evidence fixture。
- 冻结行情、财务数据与故障注入 provider。
- WIKI-UPDATE-01 和 REPORT-CHECK-01 的 task-specific pytest。
- DATA-RECOVER-01 的 recovery trace assertion。
- `business-capability-v1` suite 和独立汇总。

验收：

- 6 个业务任务均通过 `validate-task`。
- 参考实现在全部业务任务上通过。
- Lucas single baseline 完成 18 个业务 trial。
- 实时网络和市场变化不影响分数。
- WIKI-UPDATE-01 只修改目标 Wiki，并保留旧内容。
- DATA-RECOVER-01 能区分合理恢复、重复失败和直接放弃。

### PR 4：题库质量检查与冻结 Baseline

实现：

- 人工阅读所有失败 transcript。
- 修正歧义题目和错误 grader。
- 冻结任务、fixture、grader、suite 和 trace schema version。
- 冻结 `smoke-v1`。
- 冻结 `business-capability-v1`。
- 分别输出 smoke 和 business baseline Markdown 报告。

验收：

- 所有失败都能解释为 Agent 失败或明确的 Harness 问题。
- 没有 grader 拒绝合理答案的已知案例。
- 相同配置可以 rerun，且不覆盖历史结果。
- Smoke 与业务结果不合并成一个难解释的总分。

## 15. 测试策略

Eval Harness 自身必须先于 Agent 被测试：

- TaskSpec 缺字段时拒绝加载。
- TaskSpec/grader/suite 出现未知字段、重复 ID 或不支持 version 时拒绝加载。
- fixture 不存在时失败。
- grader 正确接受 reference、拒绝 bad fixture。
- process grader 只读取 trace，不解析 Python log。
- timeout 能终止测试进程。
- 临时工作区隔离。
- forbidden path 和 symlink escape 被拒绝。
- trace sequence 单调递增。
- trace schema version 不支持或 artifact 引用不存在时校验失败。
- started event 缺少对应 finished/error 时校验失败。
- `run_finished` 缺失、重复或不是最后事件时校验失败。
- allowed_tools、max_steps、no_repeated_failure、finish_reason 均有正反测试。
- recovery_assertion 覆盖恢复成功、重复失败和直接放弃三种情况。
- Agent 异常时仍写出 result 和 run_finished。
- deterministic FakeModel 完成 `model -> tool -> observation -> model -> finish` 集成测试。
- model error、timeout、cancellation 后无残留进程，且下一个 run 可正常执行。
- suite 中单题失败不阻断其他任务。

真实 LLM trial 不进入默认单元测试；通过显式命令运行。

## 16. MVP Definition of Done

### 16.1 Eval Infrastructure / Smoke DoD

- 6 个 smoke tasks 均通过 `validate-task`。
- 默认产品配置处于 single 模式。
- single research 不 spawn 多 researcher、不调用多 Agent synthesis。
- multi 模式仍可显式开启并通过原有测试。
- 每题都有参考实现。
- 参考实现在所有任务上 100% 通过。
- Lucas single baseline 完成 18 个 trial。
- 每个 trial 从干净 fixture 开始。
- 每个 trial 有 manifest、trace 和 result。
- 产品 single path 与 Eval Adapter 复用同一个 iterative AgentRunner；PR 0 的一次性 research call 不作为影子 baseline。
- required outcome grader 决定最终 success。
- 安全失败是硬失败。
- Required process constraint 失败时整体失败。
- TraceRecorder 从 PR 1 开始存在。
- 每条 trace 都有唯一 run_id、sequence、timestamp 和 event type。
- manifest/event 包含受支持的 trace schema version，artifact 引用可解析且 hash 匹配。
- model/tool started 都有 finished 或 error。
- 能汇总 success、steps、latency、tool calls、token/cost。
- 能汇总 process violations 和 repeated failures。
- 能分别汇总 provider retry、tool retry 和 model correction；MVP 不把它们混成一个 retry 数字。
- `EDIT-01` 能单独证明写文件/patch 和禁止无关修改检查正常。
- 生成并保存第一份 smoke baseline 报告。

### 16.2 Business Capability Baseline DoD

- 6 个 business capability tasks 均通过 `validate-task`。
- 每题都有参考实现，且参考实现 100% 通过。
- Lucas single baseline 再完成 18 个业务 trial。
- WIKI-UPDATE-01 只修改目标 Wiki，并保留旧章节、frontmatter、日期和来源。
- STOCK-QUOTE-01 与 FINANCIAL-01 使用冻结数据并返回 `as_of/source`。
- REPORT-CHECK-01 能通过 outcome grader 验证错误确实被修正。
- DATA-RECOVER-01 的 trace 能区分恢复、重复失败和放弃。
- Smoke 与 business capability 分别汇总，不混成单一总分。
- 生成并保存第一份 business capability baseline 报告。

### 16.3 共同质量门槛

- 所有失败 transcript 被人工查看一次。
- `raw/` 和真实项目文件没有被修改。
- 相同 task、agent、model、工具和预算可以 rerun，且不覆盖历史 trial。

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

只有建立 baseline 后，才进入独立 Validator、revision、Context 和 MCP 实验。每个实验先决定保留、修改或删除，再确定下一个实验的 base variant；不预设 Planner 一定保留。

多 Agent 不作为 MVP 后的第一个实验。建议顺序是：

```text
single baseline
  -> baseline vs +planner
  -> retained variant vs +validator+revision
  -> retained variant vs +deterministic context selection
  -> context selection vs +one-time compression（仅有真实超预算失败时）
  -> native tools vs MCP adapter
  -> single vs multi
```

当 single Agent 的 Tool、Loop、Trace 和 Eval 都能解释清楚后，再让 multi 模式跑同一套业务任务，比较额外成功率是否值得增加的模型调用、latency、token、分歧处理和聚合复杂度。

## 18. 参考项目

- [Lucas 开源标杆审查](agent-harness-open-source-review.md)：本次固定 commit、源码证据、采用与不采用结论。
- [mini-swe-agent `388da74`](https://github.com/SWE-agent/mini-swe-agent/tree/388da74aad620a384ab47669b17c52133e30e7c3)：最小 Agent/Model/Environment loop 与 trajectory/limit 测试。
- [Codex `3151954`](https://github.com/openai/codex/tree/315195492c80fdade38e917c18f9584efd599304)：生产级 step/tool context、retry、trace 和 integration test 切片；不整体仿制。
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)：Task、Trial、Grader、Transcript、Outcome 和 Eval Harness 定义。
- [Inspect AI `8117bf2`](https://github.com/UKGovernmentBEIS/inspect_ai/tree/8117bf2ff6acc41de137026e2355dec1c0212dfc)：Task、Dataset、Solver、Scorer、Log、sandbox 和 limits 分层。
- [PydanticAI `8481c72`](https://github.com/pydantic/pydantic-ai/tree/8481c72789374a5af071be2864b1c8b566a0ff5b)：严格 schema、usage limits、model correction 与 Eval definition/execution/report 分离。
- [Terminal-Bench](https://github.com/harbor-framework/terminal-bench)：一题一环境、test script、oracle solution。
- [Harbor](https://github.com/harbor-framework/harbor)：后续容器化和规模运行参考。
- [SWE-bench](https://github.com/SWE-bench/SWE-bench)：fail-to-pass 与 pass-to-pass 测试思路。
- [ToolSandbox](https://github.com/apple/ToolSandbox)：后续有状态工具任务参考。

这些项目用于学习设计，不作为 Eval MVP 的首轮强依赖。

# Lucas Agent Instructions

## 1. 项目方向

Lucas 是一个通过真实业务“干中学”的 Agent Harness 练习项目。业务功能是验证 Agent 机制的试验场；长期学习对象包括 Planning、Tool、Context、Loop、Memory、Validation、Reliability、Evaluation 和 Trace。

详细目标、阶段和实验设计见 `docs/agent-harness-learning-roadmap.md`。不要因为路线图中存在某项长期能力，就在当前任务中主动实现；始终以用户当前请求为边界。

## 2. 不可违反的约束

- `raw/` 是用户提供的不可变原始输入。Codex 不得修改或删除，Lucas 运行时也不得向其中写入；抓取资料、生成报告和临时文件必须写入各自的派生目录。
- 每个 prompt 模板和内联 LLM 调用都必须用 `llm-weight: heavy|medium|light` 标注复杂度。
- 决策策略、任务拆解和输出行为优先通过 `prompts/` 下的模板调整。
- 执行语义、状态、安全、权限、超时、重试和可靠性必须由代码保证，不要只写进 prompt。
- 修改 `prompts/harness/lucas-system-prompt.md`、`prompts/harness/agent-loop.md` 等核心 prompt 时，避免"头痛医头，脚痛医脚"：从整体结构出发做精简，不在末尾追加补丁。新增指令前先检查是否与已有内容重复或矛盾。
  - `lucas-system-prompt.md`：全局行为原则（何时用工具、如何规划、wiki 约定、回答规范、底线等），不放格式约束。
  - `agent-loop.md`：输出格式和硬约束（JSON schema、单轮一工具、重试规则、路径规范等），不重复 system prompt。
- Git commit message 均使用中文，例：feat: 新增产品功能, fix: 修复问题, refactor: 代码重构, docs: 文档变更。

## 3. 先判断当前任务类型

### 普通产品功能、Bugfix 或文档任务

- 完成用户要求的最小闭环，不扩大为 Harness 建设。
- Bugfix 先写或找到能复现问题的测试，再修复并验证。
- 产品功能围绕明确的成功标准实现和测试。
- 文档任务只修改必要文档，不顺手改代码。

### 干中学输出

- 完成一个较大的产品功能或涉及关键设计决策的改动后，输出一份简短教程/解释，用浅显易懂的语言解释实现中涉及的核心原理、关键设计决策及其取舍理由。
- 小改动（如加一个参数、修一个 Bug、改一行配置）不需要输出教学文档。
- 教程写入 `docs/learnings/` 目录。
- 文件名格式：`YYYY-MM-DD-功能简述.md`。

### Agent 机制实验

当任务的目的在于验证 Planning、Tool、Context、Loop、Memory、Validation、Reliability、Evaluation 或 Trace 等机制时，采用 eval-driven 流程：

1. 写清机制假设和预期改善的指标。
2. 增加或选择能暴露问题的固定 task 和 grader。
3. 在相同模型、工具、环境和预算下运行 baseline。
4. 实现能验证假设的最小改动。
5. 对相同任务运行多次 trial，比较成功率、稳定性、步骤、延迟和成本。
6. 以环境最终状态（outcome）作为主要验收，用 transcript/trace 解释原因。
7. 实验报告写入 `docs/experiments/` 目录，运行日志追加到 `docs/experiments/experiment-log.md`。
8. 根据实验结论决定保留、修改或删除该机制。

如果 Evaluation Harness 尚未支持所需能力，只补当前阶段需要的最小 task、grader 和运行记录；不要因此提前建设完整框架。

评估时遵循：

- 优先使用确定性 grader，例如测试、文件状态、schema 和禁止变更检查。
- 只有主观质量无法客观判断时才使用 LLM grader，并允许返回“不确定”。
- 不要规定固定工具调用路径，除非该路径本身属于安全、权限或任务要求。
- Capability suite 用于测量尚不稳定的能力；稳定通过的任务进入 regression suite。

#### Agent 级与组件级 eval 分开存放

判定只看一条：**这次运行有没有 Agent 在做决策？**

- **Agent 级** → `evals/tasks/`。由 `AgentRunner` 驱动，必须有 `task.yaml`，注册到 `evals/suites/*.yaml`，由 `evals/harness/grader.py` 判卷。被测对象一定是生产实现。
- **组件级** → `evals/components/`。独立 `run_*.py` 直接调函数算 Recall/MRR 等指标，不启动 Agent、无需 `task.yaml`、不注册 suite。被测对象**可能是为实验单独写的实现**。

不要把组件级实验放进 `evals/tasks/`，也不要为组件级实验建并行 Harness。

组件级实验额外要求：单变量；ground truth 标注在不随被测维度变化的单位上（如被测维度是 chunk 大小，则标注在文档级）；报告必须写明被测实现是否为生产实现，以及样本量是否足以支撑细粒度排序。完整规范见 `evals/components/README.md`。

组件级结论不能直接当作生产行为的结论——要判断生产是否该改，必须做 Agent 级 eval，或让组件级实验直接调用生产函数。

## 4. 通用编码规范

### 开始前先想清楚

- 明确写出必要假设，不要默默选择一种解释。
- 存在会实质改变结果的多种解释时，说明取舍；无法安全假设时再询问用户。
- 如果有明显更简单的方案，先指出并优先采用。
- 对多步骤任务，给出简短计划，每一步包含验证方式。

### 简单优先

- 只实现被要求的能力，不增加推测性的功能。
- 不为单次使用创建抽象。
- 不增加没有被要求的“灵活性”或“可配置性”。
- 只为真实、可解释的失败模式增加错误处理，最好有测试证明。
- 如果 200 行可以清晰地写成 50 行，应当重写为更简单的版本。

### 最小、外科式修改

- 只修改完成当前任务所必需的代码。
- 保留用户已有和并行进行的修改；不要清理、格式化或重构无关代码，不顺手改善相邻代码、注释或格式。
- 匹配现有项目风格，即使你个人会采用其他写法。
- 发现无关死代码时只说明，不删除。
- 删除由本次修改造成的未使用 import、变量和函数。
- 每一处改动都应能追溯到用户请求或本次改动产生的必要清理。

### 目标驱动执行

把请求转换成可验证目标：

- “增加校验” → 为无效输入写测试并使其通过。
- “修复 Bug” → 写出复现测试，修复后运行相关回归测试。
- “重构” → 确保重构前后行为测试一致。

持续执行到成功标准满足；不要把“代码已经写完”当成任务完成。

### 已知教训（渐进式加载）

改动涉及对应领域前先读教训文档，避免重复踩坑。代码踩坑记录统一放 `docs/lessons/`，按 `YYYY-MM-DD-简述.md` 命名，并在本节加一行指针：

- 前端输入框/文本域的回车提交必须抑制输入法组合回车（含组合结束短窗口），教训见 `docs/lessons/2026-08-01-前端输入法回车陷阱.md`。
- LLM 用 write_file 写 wiki 页面时，frontmatter 的 summary 值必须用英文单引号包裹；校验层要把 YAML 语法错误与字段缺失分开报错，教训见 `docs/lessons/2026-08-01-write_file-frontmatter-yaml-引号.md`。
- DeepSeek Responses 工具轮也会流式输出中间文本，须按 turn 完成时是否含 function_call 决定丢弃，教训见 `docs/lessons/2026-08-01-responses工具轮流式中间文本.md`。
- 中文散文实测约 0.60 token/字符，`DEFAULT_TOKENS_PER_CHAR = 0.35` 低估约 71%；按字符估 token 预算要留余量，别凭该常量推断压缩第几步触发，教训见 `docs/lessons/2026-08-04-中文token密度与压缩触发预估.md`。
- Agent 级 eval 的 grader 若位于工作区内（如 pytest 判卷文件），不得内联期望值——Agent 有读权限就等于拿到答案；期望值应现场从 fixture 解析，具体数值钉在工作区外的测试里。

## 5. 两类 Harness 的边界

- **Agent Harness**：让模型规划、调用工具、观察结果并完成任务的运行时。
- **Evaluation Harness**：准备任务和隔离环境、运行 trial、记录 trace、自动判卷并汇总指标的系统。

两者可以共享数据协议，但不要把评估逻辑硬编码进业务 Agent，也不要让业务概念进入通用 Harness 核心。

## 6. 读懂 Trace（两类 trace 的关联）

Lucas 有两类 trace：前端 Trace 面板导出的 `lucas-trace-*.json` 是回合级决策轨迹（问题→答案、过程步骤、`model_input`/`model_output`/`assistant_answer`/`run_finished` 等 run 生命周期事件）；后端 `logs/chat-traces/<trace_id>-<slug>/` 的 `trace.jsonl` + `artifacts/input|output-step-N.json` 是每步发给模型的完整原始 context 与 usage（需 `LUCAS_CHAT_TRACE=1` 开启）。两者通过同一个 `traceId` 关联：前端导出 JSON 每轮带 `traceId`/`traceFile`，后端目录以 `<trace_id>-<slug>` 命名且 `chat_started` 记录同一 `trace_id` 与 `trace_path`，任一端都能定位到另一端——读前端 trace 看 Agent 做了什么决策，读后端 trace 看每一步模型实际看到和消耗了什么。

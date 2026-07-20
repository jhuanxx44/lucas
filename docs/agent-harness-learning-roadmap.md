# Lucas Agent Harness “干中学”优化规划书

## 1. 定位

Lucas 的长期价值不只是完成某个具体业务，而是作为一个可持续演进的 Agent Harness 练习场：通过一组固定、可验收的任务，逐步实现并验证 Agent 的计划、工具、上下文、可靠性、评估和可观测性机制。

目标不是一次性设计出“大而全”的框架，而是持续重复下面这个学习循环：

```text
提出机制假设
  -> 实现最小版本
  -> 在固定任务集上运行
  -> 查看 trace 和失败案例
  -> 用指标判断是否真的改善
  -> 记录结论并决定下一次迭代
```

第一阶段先把最小主循环做稳：

```text
model -> tool -> observation -> model -> ... -> finish
```

显式 Planner、Validator、Revision、Context policy 都作为这个主循环上的可选实验。只有 eval 证明有收益，才进入保留架构；最终是否形成 `plan -> execute -> validate -> revise -> finish`，由实验结果决定，而不是路线图预设。

## 2. 非目标

第一阶段明确不做：

- 不抽象成可发布的通用 Agent Framework。
- 不引入分布式队列、数据库、容器编排或多租户。
- 不追求任意 Shell；只支持受限、可审计的测试和诊断命令。
- 不通过增加大量业务 Agent 来体现复杂度。
- 不以“回答看起来更聪明”作为主要验收标准。
- 不要求 LLM 输出逐 token 可复现；要求输入、环境、版本和评估过程可追溯、可比较。
- 不修改 `raw/`；所有 benchmark 在隔离临时工作区运行。

## 3. 总体成功标准

路线图完成后，Lucas Harness 应具备：

1. 一个边界清晰、可取消、受预算约束的最小 Agent loop，以及可插拔的 Planner、Validator、Context policy 实验。
2. 文件读取、文件写入/patch、代码搜索、受限 Shell/Test，以及至少一个 MCP Server。
3. 基于预算的 Context 选择，以及至少一次可追踪的摘要压缩。
4. run/tool/model timeout、取消、四类 retry/correction/revision、最大步数、工具错误恢复和可比较重跑。
5. 经过 reference 校验、按失败案例增长并分为 smoke、capability、regression、holdout 的固定任务集。
6. success rate、steps、latency、cost、provider retry、tool retry、model correction、revision、context size 等指标。
7. prompt、context、tool call、错误、validation、revision 和产物 trace。
8. 无后端依赖的本地 HTML replay。
9. baseline、planner、planner-validator、context-selection、context-compression 等逐项可归因对比。
10. 每次机制升级都有实验结论，而不只是代码提交。

## 4. 设计原则

### 4.1 先可测，再复杂

任何新机制先回答三个问题：

- 它要改善哪个固定任务或指标？
- 自动验收器如何判定改善？
- 失败时 trace 里应该看到什么？

无法回答时先不做抽象。

### 4.2 普通代码优先于 Agent

- 路径校验、超时、重试、预算、指标计算用确定性代码。
- 只有需要语义判断的环节才调用 LLM，例如规划、摘要、开放式 validation。
- 每个新增 prompt 或内联 LLM 调用必须标记 `llm-weight: heavy|medium|light`。

### 4.3 每个 Run 都是可审计实验

每次执行必须生成独立 `run_id` 和 manifest，记录：

- task、variant、model、temperature、seed（若 provider 支持）
- prompt 版本/hash
- tool schema/version
- fixture/version
- budgets 和 timeout
- 开始/结束时间、finish reason
- 产物和 trace 路径

### 4.4 安全边界是 Harness 的组成部分

工具安全不是外围功能。文件权限、Shell allowlist、输出截断、环境变量过滤和工作区隔离都必须进入测试集与 trace。

### 4.5 保持两条边界

建议把通用 Harness 与现有 Lucas 业务能力分开：

> 2026-07-20 更新：single 模式重构（M1–M6）完成后，`agents/` 旧业务链路（Manager + researcher DAG）已删除；产品聊天链路与 eval adapter 均直接使用 `harness/AgentRunner`，业务工具经 `harness/tools/business/` 注册。下表中的 `agents/` 一行及"Manager 作为 adapter/consumer"的表述仅为历史快照。

```text
harness/              Agent Harness 通用运行时
evals/harness/        Evaluation Harness 运行、隔离、判卷和汇总
evals/tasks/          固定 task、fixture、reference
evals/suites/         固定 suite
prompts/harness/      Harness prompt
agents/               现有 Lucas 业务 Agent
server/ + web/        产品入口与 replay 入口
```

现有 Lucas Manager 后续作为 Harness 的一个 adapter/consumer，而不是继续把所有机制写进 `Manager`。

### 4.6 标杆按问题查，不按框架抄

开源参考的角色固定为：mini-swe-agent 看最小骨架，Codex 看生产边界，Inspect AI 看 Eval 边界，PydanticAI 看 schema、usage limit 和模型修正语义。只有出现具体设计问题或失败案例时才定向查看固定 commit；详细结论见 `docs/agent-harness-open-source-review.md`。

## 5. 现阶段 Agent Harness 能力基线

本节盘点的是 Lucas 作为通用 Agent Harness 的底层能力，不评价其具体业务知识或投研效果。盘点基于 2026-07-17 当前工作树；其中包含尚未提交但已存在于工作区的会话持久化、LLM 流式修复和数据源相关改动。

> 2026-07-20 更新：本节（含 5.2 执行拓扑、5.3 能力总表、5.4 中对 `agents/manager.py` 的分析）是重构前快照。single 模式重构后 `agents/` 已删除，当前架构与实验结论见 `docs/plans/2026-07-20-single-mode-rewrite.md` 与 `docs/harness/experiment-log.md`。

### 5.1 成熟度标尺

| 等级 | 含义 |
|---|---|
| L0 缺失 | 尚无实现或只有文档设想 |
| L1 雏形 | 有局部代码，但没有形成可独立验证的能力 |
| L2 部分可用 | 能在特定路径工作，协议、边界或失败处理不完整 |
| L3 可用 | 主路径稳定，有基础测试，可以作为后续改造起点 |
| L4 可实验 | 有固定任务、指标和 trace，可做版本对比 |
| L5 可依赖 | 经过系统评估，边界、恢复和可观测性完整 |

从 Harness 角度，Lucas 当前整体处于 **L2，约 40% 完成度**：已经有路由、工具循环、多 Agent 编排、局部校验和文件型状态，但没有统一运行时、显式 revision、benchmark、trace/replay 和 MCP。

这里的 40% 不表示代码量，而表示距离“可以持续做 Agent 机制实验”的距离。Lucas 作为具体应用的完成度高于这个数字，但作为 Harness，缺少的正是评估和可观测性等关键基础设施。

### 5.2 当前执行拓扑

当前主入口不是一个统一状态机，而是一次路由后进入不同的固定执行路径：

```text
HTTP/SSE request
  -> 每次请求创建新的 Manager
  -> dispatch LLM 一次性选择 action
       -> direct: 最多 5 轮 prompt-based tool loop
       -> research: parallel/serial researchers -> verify -> synthesize
       -> compile: 固定编译流程
       -> ingest: 固定收录流程，可暂停等待人工分类
  -> persist memory/report/wiki
  -> finish
```

它已经包含 `observe -> tool -> observe` 的局部循环，但整体还不是：

```text
plan -> execute -> validate -> revise -> finish
```

主要差异是：dispatch 后计划基本冻结；validation 只产生置信度和警告，不会触发 replan 或重新执行。

### 5.3 能力总表

| 维度 | 当前等级 | 已有能力 | 关键缺口 | 对应路线图 |
|---|---:|---|---|---|
| Planning / Routing | L3 | LLM 能选择 action、研究员、并行/串行模式，并拆分子任务 | 没有 Plan/Step 生命周期、success criteria、动态 replan | Phase 2 |
| Execute Loop | L2 | Direct 路径最多 5 轮工具调用；研究路径支持 fan-out/fan-in | 主流程是固定 DAG；没有统一状态机、step 状态和 revision | Phase 0、2 |
| Tool Runtime | L2 | 有工具注册、描述、统一 execute 和基础路径检查 | 只有文本协议；缺 JSON Schema、结构化 ToolResult、权限、timeout、幂等性 | Phase 1 |
| 文件与代码操作 | L1 | 能列目录、读文件、关键词搜索 | 没有写文件、patch、`rg` 级代码搜索、受限 shell/test | Phase 1 |
| MCP | L0 | 无 | 没有 client、server config、工具发现、调用和断连恢复 | Phase 5 |
| Context 管理 | L2 | 不同来源有固定截断；Wiki 有 top-k 召回 | 没有统一 token budget、选择记录、去重、压缩和 provenance | Phase 4 |
| 短期 Memory | L2 | 能注入最近对话；会话消息可持久化 | Manager 每次请求重建；摘要只是 200 字截断，没有重要性策略 | Phase 4、9 |
| 长期 Memory | L2 | 偏好与历史结论落盘，可跨请求使用 | 子串召回、覆盖式偏好、无时间衰减和写入决策 | 后续扩展，不阻塞核心 Harness |
| 多 Agent 编排 | L3 | 动态选人、并行、串行、并发限制、单研究员错误隔离 | 尚未与 single 在同一 runtime、工具、预算和 grader 下比较 | Phase 8、9 |
| Validation | L2 | URL、部分数字和输出置信度有事后校验 | 校验覆盖窄；不基于任务 success criteria；不触发修正 | Phase 2 |
| Revision / Reflection | L1 | synthesis 会比较分歧，工具参数可由下一轮模型自行调整 | 没有显式 revision decision、失败归因、重复失败防护 | Phase 2、3 |
| Timeout / Retry | L2 | 部分 HTTP 有 timeout；Gemini 非流式调用有局部 retry | 没有 baseline 可靠性地板；四类 retry/correction/revision 语义混杂 | Phase 0、3 |
| 错误恢复 | L2 | 单研究员失败不拖垮其他研究员；工具异常转为文本；待确认任务可恢复 | 错误未分类；没有 transient/permanent/denied 语义和任务 checkpoint | Phase 1、3 |
| 可重复运行 | L1 | 本地单用户、文件状态直观 | 没有 run manifest、fixture 隔离、版本/hash、rerun 命令 | Phase 0、3 |
| 自动评估 | L1 | 有单元/API 测试 | 没有固定 Agent task、grader、suite 和 holdout | Phase 0、6 |
| Metrics | L1 | 非流式 LLM 能提取 token/latency；报告有 total_tokens 字段 | 流式研究 token 为 0；没有 steps、retry、context、分层 latency 指标 | Phase 0、7 |
| Trace | L1 | 有日志、SSE 状态事件、报告/sidecar 产物 | 没有 versioned append-only run trace、artifact 引用和 prompt/tool/context 关联 | Phase 0；Phase 7 只做增强与 replay |
| Replay | L0 | 无 | 无法离线还原一次执行为何成功或失败 | Phase 7 |
| Human-in-the-loop | L2 | 材料分类支持 pending、TTL、用户选择后恢复 | 是业务专用实现，没有通用 pause/resume 协议 | Phase 3、9 |
| 模型抽象 | L3 | Gemini 与 OpenAI-compatible 统一接口，多 provider 配置 | retry、usage、stream 行为不一致；无 provider fallback | Phase 3 |
| 安全边界 | L2 | 部分路径穿越检查，Wiki API 有安全测试 | 无 per-run sandbox、shell allowlist、环境变量过滤和统一权限模型 | Phase 1 |
| 工程测试基线 | L3 | 37 个非真实 LLM 测试通过 | 无 Agent E2E benchmark；前端仍有 1 个 lint error | Phase 0、6 |

### 5.4 Planning 与 Loop 现状

#### 已有实现

`agents/manager.py::_dispatch` 已经是一个一次性轻量 Planner：

- 在 direct、research、compile、ingest 等 action 之间路由。
- 选择参与的 researcher。
- 决定 parallel 或 serial。
- 为不同 researcher 生成 `sub_question/focus/avoid`。
- JSON 解析失败时回退到全部 researcher。

`agents/manager.py::_tool_use_loop` 是当前最接近 Harness baseline 的部分：

- 模型返回 `answer` 或 `tool`。
- 执行工具后把 observation 加回 prompt。
- 最多运行 5 轮。
- 未知工具或参数错误以文本形式返回，模型理论上可在下一轮修正。

#### 当前边界

- dispatch 结果没有 `plan_id`、step id、依赖关系、expected output 和 success criteria。
- 执行过程中不会根据 observation 修改完整计划。
- 没有“当前步骤已完成”的确定性状态，只依赖模型选择 answer。
- 达到最大轮数只返回固定失败文案，没有结构化 finish reason。
- 研究工作流只有 parallel/serial，属于固定 fan-out/fan-in。
- validation 后不会 revise；researcher 输出有错时仍会进入 synthesis。

#### 可复用判断

Direct loop 适合作为 Phase 0 的 `baseline` 行为参考，但不建议直接继续扩写 `_tool_use_loop`。更好的方式是抽出独立 Runner，再让当前 Manager 作为调用方。

### 5.5 Tool 能力现状

#### Manager 可直接调用的工具

| 工具 | 能力 | 返回形式 |
|---|---|---|
| `list_files` | 列目录和文件大小 | 文本 |
| `read_file` | 全文截断或关键词上下文 | 文本 |
| `search_files` | 文件名和内容子串搜索 | 文本 |
| `recall` | 历史结论子串召回 | 文本 |

此外，researcher 内部会隐式调用网络搜索和结构化数据源，但这些不是 Manager 可统一发现和调度的工具。

#### 已有基础

- 有简单工具注册表和统一 `execute(name, args)`。
- 有参数说明，LLM 通过 JSON 选择工具。
- 读取路径有基础越界检查。
- 工具抛出的异常会转成错误文本，不直接终止进程。

#### Harness 缺口

- 没有标准 `ToolSpec` 和 JSON Schema。
- 没有标准 `ToolResult`；成功和失败都是自然语言字符串。
- 没有 `error_code`、duration、truncated、artifact 等字段。
- 没有 read/write/process/network 权限声明。
- 没有工具级 timeout、retry、幂等性和取消。
- 没有运行隔离或 writable roots。
- 没有写文件、patch、受限 test/shell。
- 没有 MCP adapter。
- 搜索使用 Python glob + 子串扫描，不等同于稳定、受限的 `rg` 代码搜索工具。

因此当前 ToolKit 应视为 Tool Runtime 的原型，而不是在其上继续堆所有工具。

### 5.6 Context 管理现状

当前 Context 来自：

```text
用户问题
+ 浏览器历史
+ Manager conversation memory
+ preferences
+ historical conclusions
+ Wiki context
+ 网络搜索
+ 结构化数据
+ 前序 researcher 输出
+ tool observations
```

已有的局部控制规则：

| 来源 | 当前限制 |
|---|---|
| HTTP 对话历史 | 取最近 10 条 |
| Manager conversation | 默认最近 5 个 turn |
| 单条 conversation summary | 截断为 200 字 |
| Wiki | 最多 3 页，每页最多 3000 字 |
| 网络搜索 | 默认 5 条结果 |
| `read_file` | 默认最多 4000 字 |
| Raw 编译 | 单文件取前 8000 字 |
| Direct tool observations | 每轮持续追加，无统一预算 |
| Serial researcher | 前序输出全文注入 |

这些数字能避免最明显的上下文爆炸，但它们散落在各模块中，并不构成 Context Manager。

当前缺少：

- 统一 token budget 和 tokenizer/估算器。
- ContextItem id、来源、相关性、优先级和 provenance。
- 选中/丢弃原因。
- 重复内容检测。
- 按当前 step 选择上下文。
- 超预算摘要。
- 压缩前后指标。
- 防止 validator feedback、最近错误等关键信息被裁掉的规则。

### 5.7 Memory 与持久化现状

当前存在四类状态：

1. `ManagerMemory._conversation`：请求生命周期内的短期上下文。
2. `memory/preferences.yaml`：覆盖式用户偏好。
3. `memory/conclusions.jsonl`：最多 50 条历史结论。
4. `memory/sessions/*.json`：当前工作树新增的持久化会话和消息。

#### 已有基础

- preferences、conclusions、sessions 都可跨进程保存。
- 会话文件采用临时文件 + `os.replace`，避免部分写入。
- 会话支持创建、读取、排序、重命名、替换消息和删除。
- 用户传入的历史会重新注入新建的 Manager。

#### Harness 缺口

- 这些是产品状态，不是 Agent run checkpoint。
- 没有保存 plan、当前 step、tool observations、retry 和 validation 状态。
- 中断后只能重新执行请求，不能从上一步恢复。
- 长期结论召回是 topic 子串匹配，没有 relevance score。
- 没有“是否值得写入 memory”的策略。
- 没有 episodic run memory 与 semantic memory 的区分。

第一轮 Harness 不需要先重做长期 Memory；优先建立 run state、manifest 和 trace。否则会在无法评估的情况下过早进入向量检索等复杂问题。

### 5.8 Validation、Reflection 与 Human-in-the-loop 现状

#### Validation

`utils/verify.py` 当前支持：

- 输出 URL 是否来自搜索结果。
- URL HEAD 可达性。
- 股价、PE、总市值等少量数字与结构化数据的偏差检查。
- 根据 error/warning 数量计算 confidence。

这些校验发生在 researcher 输出完成之后。结果用于 synthesis 提示和报告归档，但不触发重新搜索、重跑 researcher 或修改答案。

因此它是 **post-hoc verification**，不是闭环 Validator。

#### Reflection

综合 prompt 会比较多个 researcher 的共识、分歧和视角局限，属于内容层 reflection；但系统没有独立记录：

- 哪个 success criterion 未满足。
- 失败属于 planning、context、tool 还是 output。
- 下一轮具体修改什么。
- revision 后是否真正改善。

#### Human-in-the-loop

材料分类不确定时，系统会保存 pending 状态，向用户展示候选项，并在用户选择后恢复。这证明 Lucas 已经拥有 pause/resume 的业务雏形。

但 pending schema、TTL、resume payload 都写在 Manager 内部，不能复用于工具授权、计划选择、冲突裁决等通用场景。

### 5.9 Reliability 与错误恢复现状

#### 已有基础

- Gemini 非流式调用对部分可重试错误做有限 retry。
- Web、URL 下载和 URL 验活设置了各自 timeout。
- 多 researcher 运行时有并发上限 2。
- 单 researcher 异常会生成失败结果，其他 researcher 继续。
- Direct 工具错误会变成文本 observation。
- Pending ingest 有 TTL 和歧义检查。
- Wiki 写入前有 `.bak` 备份，session 写入使用原子替换。

#### 主要缺口

- 没有统一 run timeout。
- model、stream、tool、subprocess 的 timeout/retry 语义不一致。
- 错误没有统一分类为 invalid/denied/timeout/transient/permanent。
- 没有根据幂等性决定能否 retry。
- 没有全局 max steps、max revisions、token 或 cost budget。
- 没有防止“相同工具 + 相同参数 + 相同错误”连续重复。
- 没有 checkpoint、resume 或 manifest-based rerun。
- 没有故障注入任务验证恢复行为。

### 5.10 Metrics、Trace、Replay 与 Eval 现状

#### Metrics

现有 `TokenUsage` 能记录非流式调用的 prompt、completion、thinking、total token 和 latency，并能做粗略成本计算。

但当前 researcher 使用流式调用，`ResearchResult.token_usage` 被固定为 `None`，所以研究主流程的 `total_tokens` 通常为 0。系统尚未统计：

- steps
- tool calls
- retry
- context before/after
- revision
- finish reason
- 分层 model/tool/validation latency

#### Trace

当前可观察信息分散在：

- Python logging。
- SSE status/researcher/synthesis 事件。
- 最终 Markdown 报告、meta、evidence/claims sidecar。

这些信息没有统一 `run_id`、sequence、parent event 和 schema，无法完整关联一次运行中的 prompt、context、tool call、错误和产物。

#### Replay

当前没有 replay。日志和报告只能看到部分结果，不能回答：

- Planner 当时看到了什么？
- 为什么选择这个工具？
- 哪段 Context 被丢弃？
- retry 发生在哪里？
- Validator 为什么要求 revision？
- 最终失败是模型、工具还是 grader？

#### Eval

当前工程基线是：

- 37 个不调用真实 LLM 的后端测试通过。
- 流式客户端、路由、待确认任务、sidecar、会话、Wiki API 等已有局部测试。
- 前端仍有 1 个 React lint error。
- `tests/test_llm_connectivity.py` 是手动连通性脚本，不属于稳定自动 benchmark。

缺少分层、固定版本的 Agent tasks、自动 grader、suite、variant 和成功率报告。因此现有测试能证明函数/API 没明显回归，不能衡量 Agent 是否更会完成任务。

### 5.11 可直接复用的资产

路线图不需要把现有代码全部推倒。以下资产适合作为学习起点：

| 现有资产 | 可复用方向 | 不应直接继承的限制 |
|---|---|---|
| `_tool_use_loop` | Baseline 行为和 smoke task 参考 | 不继续扩成巨型 Runner |
| `dispatch.md` | Planner prompt 的案例 | 输出要升级为 Plan/Step/success criteria |
| `ToolKit` | 工具注册和路径检查经验 | 迁移到 ToolSpec/ToolResult，不沿用文本错误协议 |
| `LLMClient` | Model adapter 起点 | 统一 stream usage、timeout、retry 和 trace hook |
| `ResearchService` | 并发、串行和错误隔离经验 | 不把业务 researcher 直接放进通用 Harness |
| `verify.py` | 确定性 Validator 案例 | validation 必须基于任务 criteria 并能触发 revision |
| `ManagerMemory` | 短期/长期状态拆分经验 | Harness 优先做 run state，不先重做语义 memory |
| `SessionStore` | 原子文件持久化案例 | Session 不等于 run checkpoint |
| `TokenUsage` | cost/latency 指标起点 | 补齐 streaming、step、tool、context 指标 |
| SSE event | 事件化展示经验 | Trace 必须 append-only、可关联、可离线 replay |
| Pending ingest | pause/resume 案例 | 后续抽象为通用 HumanInputRequest |

### 5.12 从现状到目标的最短路径

按依赖关系，最短路径不是先升级 Memory 或多 Agent，而是：

```text
产品 single|multi 执行边界（PR 0）
  -> Eval 考场、Oracle、严格 TaskSpec 与 grader
  -> 共享最小 AgentRunner + ModelAdapter + Environment/ToolRuntime
  -> 可靠性地板 + versioned TraceRecorder
  -> smoke-v1 与 business-capability-v1 baseline
  -> 冻结 baseline 与失败分类
  -> 扩展 Tool contract / safety
  -> Planner 单变量实验
  -> Validator + Revision 单变量实验
  -> Context selection，再单独实验 compression
  -> 接 MCP
  -> 按失败案例扩充 capability/regression/holdout
```

原因是：没有 run、trace 和 grader 时，Memory、Context 或 Planner 的改动都无法证明是否改善；没有 timeout、取消、输出上限和清理时，baseline 本身也不可信。

## 6. 目标架构

```text
Evaluation Harness
  TaskSpec / fixture / reference
      -> EvalRunner -> AgentAdapter ----------------------------+
                                                               |
Agent Harness                                                  |
  AgentRunner                                                  |
      -> immutable StepContext                                 |
      -> ModelAdapter                                          |
      -> Environment / ToolRuntime                             |
      -> TraceSink + artifact store                            |
      -> RunResult --------------------------------------------+
                                                               |
Optional experimental policies                                |
  Planner | Validator/Revision | Context selection/compression |
                                                               v
                                                external Graders -> Report
```

`AgentAdapter` 是 Eval Harness 调用被测 Agent 的边界，不承担模型格式、工具执行和预算。Planner、Validator 和 ContextManager 不进入 baseline 的必选依赖；它们通过配置组合在同一个 Runner 上实验。

### 6.1 核心状态机

Baseline 第一版：

```text
INIT -> MODEL_CALL -> TOOL_CALL -> MODEL_CALL -> ... -> FINISH
任意状态 -> timeout / budget / max_turns / cancelled / fatal_error -> TERMINAL
```

Planner variant 可以在 `MODEL_CALL` 前产生或更新 Plan；Validator variant 可以在候选 finish 后返回 pass/revise/fail。二者不得改变 baseline 的 timeout、tool、trace 和 terminal 语义。

Phase 0 核心对象只包含：

```python
RunState
StepContext
RunResult
TraceEvent
```

`RunState` 只保存 messages、step/model call/correction counters、usage、deadline/cancellation 和 terminal result。`StepContext` 固定一次模型请求看到的 context、tool specs 和预算快照。Plan、ContextItem、ValidationResult 到对应实验再加入。不要在第一版增加 message bus、blackboard、agent graph。

## 7. 分阶段路线图

以下阶段按依赖顺序排列。每个阶段都必须完成“实现、固定任务运行、失败复盘、结论记录”四件事。

---

## Phase 0：冻结 Baseline 与实验协议

### 学习问题

- 没有显式 planner、validator 和 context compression 时，当前最小 Agent 能做到什么？
- 如何保证后续改动比较的是机制，而不是任务、模型或 prompt 偷换？

### 最小实现

Phase 0 按 `docs/agent-harness-eval-mvp.md` 的 PR 0—4 实施，MVP 术语与目录以该文档为准。

1. 在 `evals/` 下建立 `harness/`、`tasks/`、`suites/` 和 CLI：

   ```bash
   python -m evals.harness run-suite evals/suites/smoke.yaml \
     --agent lucas-single --trials 3
   ```

2. 定义严格、拒绝未知字段且带 version 的 `TaskSpec/RunLimits/Trial/AgentResult/GradeResult`。
3. 抽出产品与 Eval 共用的最小 `AgentRunner/ModelAdapter/Environment/TraceSink`；当前 `SingleAgentService` 的一次性 research call 只是 PR 0 边界，不等于最终 baseline loop。
4. Baseline 采用最小 tool loop，不生成显式 plan，不做独立 validation，不压缩 context。
5. 加入可靠性地板：max model turns/corrections、run/model/tool/subprocess timeout、cancellation、输出上限、进程清理和结构化 finish reason。
6. Trace 从第一轮使用 versioned append-only JSONL；大 payload 先写 artifact，再写 hash/path 引用。
7. 先用 deterministic FakeModel 做 loop integration test，再运行 6 个 smoke 和 6 个 business capability tasks。

### Baseline 固定项

- 同一个模型和 provider。
- temperature 固定为 0 或 provider 可用的最低值。
- 相同的 system prompt、工具集合、任务 fixture。
- 相同 max steps、timeout 和 context budget。
- 相同 provider/model retry 配置；model correction 与 provider retry 分别计数。
- 保存 prompt hash、Git commit/dirty 状态、依赖版本、TaskSpec/grader/trace schema version。

### 验收

- 6 个 smoke tasks 与 6 个 business capability tasks 可以分开运行和汇总。
- 每个 run 都有唯一目录和机器可读结果。
- 失败、timeout 或 cancellation 也能留下唯一 terminal event、完整 finish reason，并释放运行状态与子进程。
- 同一任务连续运行 3 次，不会污染 fixture 或其他 run。
- deterministic loop integration test 能验证 tool call id/observation 会进入下一次模型请求。

### 阶段产物

- `evals/harness/`
- `evals/suites/` 与 `evals/tasks/`
- 共用的最小 `harness/runner.py`、ModelAdapter、Environment/ToolRuntime 与 TraceSink
- `runs/<run_id>/manifest.json`
- smoke 与 business capability 两份 baseline 记录

---

## Phase 1：Tool Runtime 与安全边界

### 学习问题

- LLM 工具调用与普通函数调用相比，需要增加哪些协议？
- 如何让工具错误可恢复，而不是变成一段不可解析的字符串？
- 如何限制 Agent 对本地环境的影响？

### 最小工具集

| Tool | 能力 | 默认权限 |
|---|---|---|
| `read_file` | 读取文本、行范围、大小限制 | benchmark workspace 内只读 |
| `write_file` | 新建或整体写入 | 仅 writable roots |
| `apply_patch` | 小范围编辑 | 仅 writable roots |
| `search_code` | `rg` 文件名/内容/正则搜索 | workspace 内只读 |
| `list_files` | 目录浏览 | workspace 内只读 |
| `run_tests` | 运行预定义 pytest/npm test target | allowlist、无 shell 插值 |
| `shell_info` | `pwd`、`git status --short` 等诊断 | 严格 allowlist |

### ToolSpec

每个工具至少声明：

```text
name
description
input_schema
output_schema
permissions: read | write | process | network
idempotent
default_timeout_ms
max_output_chars
version
```

### ToolResult

禁止只返回任意字符串。统一状态与三种输出视图：

```text
status: ok | invalid_input | denied | timeout | transient_error | permanent_error
structured / raw_artifact: 完整结构化结果或 artifact 引用
observation: 有硬上限，返回模型
trace_preview: 脱敏且有硬上限
error_code
duration_ms
truncated
artifacts
```

artifact 必须先持久化，再让 trace 或 observation 引用其 hash/path。工具策略、trace 和执行器接收同一个 `StepContext`，不得依赖可变全局状态。

### 安全要求

- 所有 benchmark 从 fixture 复制到临时目录运行。
- 禁止访问临时目录外路径，额外显式禁止 `raw/`。
- 子进程使用 argv，不用 `shell=True`。
- 清理敏感环境变量，只传白名单。
- 默认断网。
- 限制 stdout/stderr 大小。
- 限制进程运行时间和并发数。
- trace 记录 denied 操作，但不泄露敏感值。

### 验收

- 路径穿越、symlink escape、禁止目录写入均被拒绝。
- 超长工具输出会截断，并保留 `truncated=true`。
- 测试超时后子进程被终止，不残留后台进程。
- 工具参数错误可以被 Agent 观察并在下一步修正。
- 重复运行不会复用上一轮临时文件。

---

## Phase 2：Planner 单变量实验

### 学习问题

- 显式 plan 是否减少无效步骤？
- 它是否只帮助多步骤任务，却让简单任务过度规划？
- plan 的哪部分信息真正被 Executor 使用？

### Planner

Planner 输出稳定 JSON：

```json
{
  "goal": "...",
  "success_criteria": ["..."],
  "steps": [
    {
      "id": "step_1",
      "description": "...",
      "expected_output": "...",
      "allowed_tools": ["search_code"]
    }
  ]
}
```

建议 `prompts/harness/planner.md` 使用 `llm-weight: medium`。

### Executor

- 一次只执行一个 plan step。
- 每一步记录 observation 和 artifact。
- 工具选择仍由 LLM 决定，但受该 step 的 allowed tools 限制。
- 完成一步后更新结构化状态，不把所有历史重新拼成自由文本。

### 实验边界

- `baseline` 与 `planner` 复用同一 Runner、ModelAdapter、ToolRuntime、可靠性限制和 grader。
- planner 只新增一次显式计划及其后续更新；候选 finish 仍按 baseline 规则结束，不调用独立 Validator。
- success criteria 来自用户任务或 Planner 输出，但不得包含隐藏 grader expected value。
- plan step 的 `allowed_tools` 第一版只做收窄，不能扩张 TaskSpec 工具权限。
- 简单任务与多步骤任务分层报告，防止平均值掩盖过度规划。

### 验收

- trace 可以完整还原 plan、step 与实际 observation。
- 相同任务各运行至少 3 次 baseline 与 planner。
- 报告 success、steps、latency、token/cost，并分开简单与多步骤任务。
- 得出保留、修改或删除 Planner 的实验结论，不以“已实现 Planner”为完成。

### Thought 与 Plan 的分层共存（复杂度路由）

Thought 与 Plan 不是互斥的两种范式，而是按任务复杂度分层的两档机制，实际系统中两者共存：

- **轻档：显式 Thought（ReAct 完整形态）**。在当前单 JSON action 协议中增加 `thought` 字段，模型每步先写一句“为什么选这个动作”再给 action。改动极小（协议加一个字段 + prompt 模板一行说明），收益是推理进入 trace，可复盘“为什么选错工具”，同时零额外 LLM 调用。适合简单任务和作为所有路径的默认底座。
- **重档：显式 Plan（本 Phase 的 Planner）**。仅当被判定为复杂任务时才先产出 `goal + success_criteria + steps[]`，再逐步执行。Plan 是任务级的一次性结构，Thought 是步骤级的持续推理；启用 Plan 时步骤内仍保留 Thought。
- **路由**：由 Router（或 Runner 前置一次轻量判别，建议 `llm-weight: light`）判断任务复杂度，简单任务直接走 Thought-only 循环，复杂任务先 Plan 再执行。路由判错的代价不对称——复杂任务漏判为简单只是退回 baseline 行为，简单任务误判为复杂则浪费一次规划调用，因此路由应偏向“默认简单”。

实验顺序上，Thought 字段可作为 Phase 2 之前的过渡单变量实验（baseline vs +thought），也可以在 Planner 实验之后作为第三臂（thought-only / plan-only / 路由分层）对比。无论顺序如何，复杂度路由本身是否判得准，应通过简单/多步骤任务分层报告来验证，而不是直接假设路由正确。

### Codex 式变体：哑工具 + prompt 路由（理论上最成熟）

调研 OpenAI Codex CLI（codex-rs）后确认的第三种实现路径，工业界最成熟的方案，作为实验中的**标杆对照组**：

- **Plan 做成哑工具**：提供 `update_plan` 工具（参数为步骤列表，每项含 `step` 与 `status: pending|in_progress|completed`），harness 侧不保存 plan 状态、不强制状态机、不校验，计划完全存在于上下文中由模型自律维护。**注意不能照抄 Codex 返回固定字符串 `"Plan updated"`**：Codex 全量回放对话历史，模型的调用内容天然留在上下文；而 lucas 当前 Runner 只回放 observations（见 Phase 4「历史结构」），因此 observation 必须回显 plan 全文，否则下一轮 plan 从上下文中消失。
- **路由靠 prompt 一句话**：在 prompt 中写明“简单任务（约最简单的 25%）不要使用规划工具，不要做单步计划”，由模型自行判断任务复杂度，不做代码级复杂度判别。
- **Thought 依赖模型 API 原生 reasoning 输出**：Codex 的推理是 Responses API 的一等历史条目；若所用模型/API 支持原生 reasoning，优先直接利用，而非自造 thought 字段。

该变体的定位：不代表直接采用，而是与 baseline、重 Planner 同任务同预算对比（success / steps / latency / cost，简单与复杂任务分层报告）。若 Codex 式变体与重 Planner 效果相当，应保留更简单的 Codex 式；若重 Planner 显著更优，再保留结构化方案。另外两个可借鉴点（各自独立成实验变量，不绑定本变体）：上下文压缩复用一次普通模型调用实现（`tasks/compact.rs` 模式），而非 harness 特殊字符串处理；同一响应内多个工具调用并行执行。

---

## Phase 3：Validator、Revision 与错误恢复实验

### 学习问题

- Validator 能否把 grader 失败转为成功，还是只会自我认可？
- Revision 应修改 plan、step、工具参数还是最终答案？
- 哪些错误适合 provider/tool retry，哪些应交给模型 correction 或 revision？
- 如何避免 retry 掩盖真实失败或造成成本失控？
- 如何让两次 run 具有可比较性？

### Validator 与 Revision

Validator 分两层：

1. 确定性 validation：文件存在、内容断言、测试结果、禁止变更、schema。
2. LLM validation：只用于无法确定性判断的开放式 success criteria。

确定性逻辑优先；`prompts/harness/validator.md` 标记 `llm-weight: medium`。统一输出 `pass|revise|fail`、failed criteria、reason 与 revision scope。Revision 最多 2 次，并记录上一方案为何失败、本次改变什么。Benchmark grader 始终是最终裁判。

### Timeout 层级

```text
run_timeout
  > model_call_timeout
  > tool_call_timeout
  > subprocess_timeout
```

这些 timeout 的基本执行与清理语义已在 Phase 0 存在；本阶段补齐故障注入、分类恢复和可比较策略。所有 timeout 必须产生结构化错误和 trace event。

### Retry / Correction / Revision 分类

| 类型 | 是否增加模型步 | 自动执行条件 | 独立计数 |
|---|---:|---|---:|
| provider retry | 否 | 明确 429/5xx/断连等 transient error | 是 |
| tool execution retry | 否 | 幂等且确认上次未成功 | 是 |
| model correction | 是 | schema、format、参数错误反馈模型 | 是 |
| revision | 是 | validation 要求改变 plan/step/answer | 是 |

### Retry Policy

只重试明确的 transient error：

- provider 429/5xx/连接重置。
- 幂等工具的临时 I/O 错误。

不自动重试：

- schema 错误。
- 权限拒绝。
- 路径非法。
- 测试失败。
- 非幂等写操作结果未知。

第一版参数建议：

```text
max_provider_retries = 2
max_tool_retries = 1
max_model_corrections = 3
backoff = exponential + jitter
max_steps = 12
max_revisions = 2
```

### 工具错误恢复

错误注入任务至少覆盖：

- 文件不存在后重新搜索正确路径。
- `rg` 无结果后扩大查询范围。
- 测试命令超时后改跑更小测试目标。
- 工具输出被截断后改用行范围读取。
- 写入被拒绝后改写允许目录。

### 可重复运行

每个 run manifest 保存：

- task/fixture version
- model/provider/config
- prompt 和 tool schema hash
- Git commit 与 dirty diff hash
- package versions
- budgets、timeout、retry policy
- 允许工具列表
- 随机种子（若支持）

增加：

```bash
python -m evals.harness rerun runs/<run_id>
```

`rerun` 使用原 manifest 创建新 run，不覆盖旧结果。

### 验收

- 所有注入错误都有预期 recovery 或明确 terminal reason。
- provider/tool retry、model correction 和 revision 次数可以从 trace 中分别验证。
- 非幂等工具不会被盲目重试。
- rerun 能恢复同一任务、variant、工具和预算配置。
- 报告 validator-pass/grader-fail 与 revision-recovery 指标。

---

## Phase 4：Context 选择与一次摘要压缩

### 学习问题

- 哪些 context 真正帮助任务成功？
- 当上下文超预算时，丢弃、截断和摘要哪种更有效？
- 压缩带来的信息损失如何观察？

### 历史结构：observations-only vs 全量消息回放

当前 Runner 的已知设计差距：每轮 prompt 只由 `instruction + tools_desc + observations` 渲染，模型自己说过的话（action JSON、答案草稿、推理）不会进入后续上下文。后果：模型无法引用自己之前的判断，多轮交互场景（用户针对 Agent 上一条回复追问）下 Agent 完全看不到自己说过什么。

Codex 与 mini-swe-agent 均采用全量消息回放（模型的每条消息都是历史的一等条目），这是工业界验证过的默认正确结构。lucas 当前的 observations-only 是极简实现的副作用，不是有意设计。

决策：在 Phase 4 开头先将 Runner 的历史结构改为全量消息回放（记录每轮的 assistant 消息与 observation，按序回放），作为后续所有 Context 实验的新 baseline。此改动本身是单变量实验（observations-only vs 全量回放），预期对多步骤任务的自我纠错能力有改善；若 token 成本显著上升，由本 Phase 的选择/压缩策略对冲，而不是退回丢弃历史。在此结构落地前，依赖上下文的哑工具（如 `update_plan`）必须用 observation 回显内容兜底（见 Phase 2 Codex 式变体）。

### ContextItem

```text
id
source: user | plan | tool | file | memory | summary
text
estimated_tokens
priority
relevance_score
created_at
step_id
provenance
compressible
```

### Context 选择策略 V1

先单独实验确定性选择/丢弃，不在同一改动中加入 LLM 摘要。只有 trace 证明失败来自 context 超预算，并且 selection 仍不能解决时，才进入下一小节的 compression variant。

按以下优先级构建模型输入：

1. system/tool schema：保留。
2. 当前 goal、success criteria、当前 plan step：保留。
3. 最近一次失败和 validator feedback：高优先级。
4. 当前 step 相关文件片段和工具结果：按 relevance 选择。
5. 较早 observation：可压缩。
6. 已完成步骤的冗长输出：优先移除或摘要。

ContextManager 输出 `ContextSelection`：

```text
selected_item_ids
dropped_item_ids
token_budget
estimated_tokens_before
estimated_tokens_after
selection_reason
```

### 一次摘要压缩

第一版只实现一种清晰规则：

- 当预计 context 超过预算的 80% 时触发。
- 把最早、可压缩的 observation 合并成一个 summary。
- 最近两步、当前失败、关键文件片段不得进入摘要。
- 原始 item 不删除，只在本次 prompt 中由 summary 替代。
- summary 保存 covered item ids 和 prompt hash。
- 每个 run 默认最多主动压缩一次，便于实验分析。

建议摘要 prompt：`prompts/harness/context-summary.md`，`llm-weight: light`。

### 压缩验收

- 长上下文任务会稳定触发一次 compression event。
- trace 展示压缩前后 token 数和被覆盖 item。
- summary 中的事实可以追溯到原始 observation。
- 当前错误信息、成功标准和关键代码片段不会被压掉。
- compression variant 相比无压缩版本显著降低 context size，且成功率下降在可接受范围内。

---

## Phase 5：MCP Client 与至少一个 MCP Server

### 学习问题

- MCP 工具发现、schema 和调用与本地 ToolSpec 如何统一？
- Server 断连、超时和非法结果如何进入现有错误恢复机制？
- MCP 带来的协议复杂度是否值得？

### 第一版选择

接入本地 stdio Filesystem MCP Server，只允许访问 benchmark 临时目录。选择它的原因：

- 无外部网络依赖。
- 能稳定自动测试。
- 与 native file tools 能做能力和 trace 对照。
- 可以练习 initialize、list tools、call tool、disconnect、reconnect。

### MCP Adapter

实现：

```text
MCPClientManager
MCPToolAdapter
MCPServerConfig
```

把 MCP tool 映射到统一 `ToolSpec/ToolResult`，Runner 不感知工具来自本地还是 MCP。

配置示例：

```yaml
servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "${RUN_WORKSPACE}"]
    startup_timeout_ms: 5000
    call_timeout_ms: 5000
    restart_limit: 1
```

### MCP 验收

- 能启动、发现、调用并关闭 Server。
- MCP 路径权限不能突破 benchmark workspace。
- Server 启动失败和中途退出都有结构化错误。
- 幂等调用允许重连后重试一次。
- 至少 2 个 benchmark task 强制通过 MCP 完成。
- replay 能区分 native tool call 与 MCP tool call。

后续可选扩展：GitHub 或自建知识库 MCP，但不进入首轮完成标准。

---

## Phase 6：任务集治理与按失败扩充

任务集不以数量为目标，分四层治理：

```text
smoke          验证考场、工具和 grader
capability     暴露尚不稳定、正在学习的能力
regression     已稳定通过，防止回退
holdout        同分布未调试 fixture，检查过拟合
```

Phase 0 的 `smoke-v1` 与 `business-capability-v1` 是起点。只有失败复盘暴露新机制问题，或某项能力稳定后需要防回归，才新增/迁移任务。

### TaskSpec 格式

```yaml
id: FS-01
category: filesystem
goal: 读取配置并回答指定字段
fixture: fixtures/basic_repo
allowed_tools: [read_file, search_code]
budgets:
  max_steps: 6
  max_context_tokens: 12000
grader:
  type: exact_json
  expected:
    provider: deepseek
forbidden_changes:
  - raw/**
```

### 候选任务库（不是配额）

#### A. 文件系统：5 个

| ID | 任务 | 主要验收 |
|---|---|---|
| FS-01 | 找到并读取指定配置字段 | exact JSON |
| FS-02 | 按要求创建一个 Markdown 文件 | 文件内容断言 |
| FS-03 | 对目标文件做最小 patch | golden diff |
| FS-04 | 从多个同名文件中选择正确文件 | checksum + answer |
| FS-05 | 尝试写禁止目录并恢复到允许目录 | policy trace + artifact |

#### B. 代码搜索与理解：5 个

| ID | 任务 | 主要验收 |
|---|---|---|
| CODE-01 | 定位函数定义 | path + line |
| CODE-02 | 找出函数调用者 | expected set |
| CODE-03 | 找到配置到运行时的传递链 | ordered checkpoints |
| CODE-04 | 从错误信息定位相关代码 | expected files |
| CODE-05 | 判断某功能是否已实现 | evidence paths |

#### C. 测试与小修复：5 个

| ID | 任务 | 主要验收 |
|---|---|---|
| TEST-01 | 运行单个失败测试并解释原因 | test result + rubric |
| TEST-02 | 修复一个局部 bug | focused tests pass + diff scope |
| TEST-03 | 根据需求补一个测试 | expected test collected |
| TEST-04 | 测试超时后缩小测试范围 | recovery trace |
| TEST-05 | 修复后验证不修改无关文件 | tests + allowed diff |

#### D. Loop 与错误恢复：4 个

| ID | 任务 | 主要验收 |
|---|---|---|
| LOOP-01 | 初始文件路径错误，搜索后恢复 | success + recovery event |
| LOOP-02 | 初始工具参数错误，自行修正 | no repeated identical failure |
| LOOP-03 | 第一次方案测试失败，revision 后成功 | revision count = 1+ |
| LOOP-04 | 不可解任务在预算内终止 | expected finish reason |

#### E. Context：3 个

| ID | 任务 | 主要验收 |
|---|---|---|
| CTX-01 | 长日志中保留最近关键错误 | expected evidence |
| CTX-02 | 多文件资料中选择相关片段 | selected ids + answer |
| CTX-03 | 超预算并触发一次摘要 | compression event + success |

#### F. MCP：2 个

| ID | 任务 | 主要验收 |
|---|---|---|
| MCP-01 | 通过 MCP 读取并汇总目录 | MCP call trace |
| MCP-02 | MCP 断连后恢复一次 | reconnect + success |

以上 24 个只作为候选题库，不要求一次建完。新增任务必须写明它暴露的当前失败、所属 suite、确定性 grader 和 reference solution；通用机制题与 Lucas 业务题分别汇总。

### Grader 类型

- `exact_text` / `exact_json`
- `regex`
- `file_exists`
- `file_content`
- `golden_diff`
- `pytest_pass`
- `forbidden_diff`
- `trace_assertion`
- `artifact_schema`
- `rubric`：仅少量开放式任务使用 LLM judge

### Grader 原则

- 能确定性验收的绝不用 LLM judge。
- task 对 Agent 可见，grader 的关键 expected value 可隐藏。
- grader 单独运行，不相信 Agent 自报的 validation pass。
- 对代码修改同时检查 focused test 和 diff scope。
- 每个 task 至少有一个结果 grader，必要时附加安全/trace grader。

### 验收

- 所有进入 suite 的任务均能在干净环境单独运行，并通过 `validate-task`。
- grader 自身有单元测试。
- task fixture 不被 run 原地修改。
- 全量 benchmark 可输出 JSON 和 Markdown summary。
- capability 中稳定通过的任务有明确规则迁入 regression，并保留未调试 holdout。

---

## Phase 7：Trace 成熟化与本地 HTML Replay

基础 trace、manifest 和核心指标已在 Phase 0 存在。本阶段只扩展 schema、查询体验与 replay，不回头补埋点。

### 核心指标

| 指标 | 定义 |
|---|---|
| `success_rate` | grader pass 的任务数 / 总任务数 |
| `steps` | plan/execution step 数，报告 mean/p50/p95 |
| `tool_calls` | 总工具调用及按工具分类数量 |
| `latency_ms` | run、model、tool、validation 分层耗时 |
| `cost_usd` | 按模型 usage 和价格表估算 |
| `provider_retry_count` | transport/provider retry 次数 |
| `tool_retry_count` | 真实重新执行工具次数 |
| `model_correction_count` | format/schema/参数反馈后的新模型步数 |
| `revision_count` | validation 触发的 plan/step/answer 修订次数 |
| `recovery_rate` | 各类恢复后最终 grader success 的比例 |
| `context_tokens` | 候选、选择后、压缩后 token 数 |
| `compression_ratio` | after / before |
| `tool_error_rate` | 非 ok 工具结果 / 工具调用数 |
| `finish_reason` | success/max_steps/timeout/budget/error/cancelled |

### Trace Event

采用 append-only JSONL：

```text
run_started
context_candidates
context_selected
context_compressed
prompt_rendered
model_call_started
model_call_finished
provider_retry
model_correction
plan_created
step_started
tool_call_started
tool_call_finished
validation_finished
revision_created
artifact_created
error
run_finished
```

每条事件至少包含：

```text
event_id
run_id
sequence
timestamp
duration_ms（结束事件）
step_id
event_type
payload
parent_event_id
```

### Trace 安全

- 环境变量、API key、Authorization header 必须 redaction。
- 大文件和工具输出保存为 artifact，trace 中只留摘要、hash 和路径。
- prompt 可完整保存到本地，但 replay 页面默认折叠，并标记潜在敏感内容。
- benchmark fixture 中不得包含真实用户数据。

### HTML Replay V1

生成完全静态的本地页面：

```bash
python -m evals.harness replay runs/<run_id>
# 输出 runs/<run_id>/replay.html
```

页面至少包含：

- Run 概览：task、variant、成功与否、成本、耗时、steps。
- 时间线：plan、tool、validation、revision、finish。
- Prompt 面板：system/context/user/tool schema 分区。
- Context 面板：候选、选中、丢弃、压缩前后。
- Tool 面板：参数、结果、耗时、retry、错误。
- Validation 面板：criteria、结果、revision 建议。
- Artifact 面板：文件、diff、测试输出。
- 错误过滤与事件搜索。

第一版不做实时 Web 服务，不引入数据库；直接把 trace 数据嵌进 HTML。

### 验收

- 任意成功或失败 run 都能生成 replay。
- 仅查看 replay 即可回答“为什么失败、用了什么上下文、重试了几次”。
- HTML 不依赖外部 CDN，离线可打开。
- trace schema 有版本号和向后兼容策略。

---

## Phase 8：逐项版本对比与消融实验

### Variant 定义

实验不预设最终一定保留 Planner 或 Validator，而是逐个过门：

| 实验 | 对照 | 只有一个主要变量 |
|---|---|---|
| A | baseline vs planner | 显式规划 |
| B | retained variant vs +validator+revision | 内部校验与修订 |
| C | retained variant vs +context selection | 确定性上下文选择 |
| D | context selection vs +one-time compression | LLM 摘要压缩 |
| E | native tools vs MCP adapter | 工具协议来源 |
| F | single vs multi-agent | 多 Agent 编排 |

每个实验结束后先决定保留、修改或删除，再确定下一个实验的 base variant。所有 variant 通过配置组合同一个 Runner，不复制实现。

### 实验协议

- 固定当期 versioned suite，并用未调试 holdout 检查过拟合。
- 固定模型、provider、temperature、工具版本和 budgets。
- 每个实验 pair 的每个任务至少运行 3 次；根据基线方差决定是否增加 trial。
- 不一次批量跑预设的 288 runs；只有前一实验产生明确结论才进入下一实验。
- 同一任务的对照运行顺序随机或交错，降低时间和 provider 波动影响。
- 同时报告总体和分组指标，不只看平均 success rate。
- 保存失败样本列表，人工抽查至少 10 个差异案例。

### 对比表

最终报告至少包含：

```text
variant
success_rate
success_rate_by_category
steps_mean / p50 / p95
latency_p50 / p95
cost_mean / total
retry_rate
recovery_rate
context_tokens_mean / p95
revision_count_mean
```

### 需要回答的实验问题

1. Planner 是否提高复杂任务成功率？是否增加简单任务步骤和成本？
2. Validator 带来的修订有多少真正把失败变成成功？
3. Validator 是否出现自我认可但 grader 失败？
4. Context selection 是否减少 token 而不降低 success rate？
5. 摘要压缩在哪些任务中丢失关键信息？
6. retry 的恢复收益是否值得额外 latency/cost？
7. 哪些任务仍然失败于工具、Context、规划或模型能力？

### 验收

- 一条命令完成 variant benchmark 和汇总：

  ```bash
  python -m evals.harness run-experiment evals/experiments/planner.yaml --trials 3
  ```

- 报告能追溯到每个原始 run。
- 可以区分“机制改善”和“只是多花了 token/步骤”。
- 至少形成 3 条有证据的机制结论和下一轮假设。

---

## Phase 9：接回 Lucas 与持续学习

### 目标

Phase 0 已要求产品 single path 与 Eval Adapter 共用最小 Runner。本阶段只把实验保留的机制逐步应用到更多 Lucas 产品流程，并验证真实收益。

### 接入顺序

1. 确认产品 single path 与 Eval Adapter 调用同一个 AgentRunner，不维护影子实现。
2. 按业务任务需要把现有工具迁移到统一 ToolRuntime，不一次迁完全部能力。
3. 只有 Planner 实验通过，才把现有 dispatch 作为 planner adapter 的输入案例。
4. 只有 Validator 实验通过，才把现有 verify 作为 deterministic validation 的输入案例。
5. 在低风险 direct/research 任务灰度启用被保留的 policy，并与 baseline 对照。
6. trace 完成脱敏和保留策略后，再记录真实产品 run；不把真实用户数据复制进 eval fixture。
7. 最后才实验 single vs multi 和动态 replan。

### 候选业务实验：Wiki 访问策略消融

当前 `wiki_recall` 是“jieba 关键词提取 + 索引字段匹配 + 正文子串评分”，但专用召回工具未必优于 Agent 自主组合基础文件工具。等 Evaluation Harness 的任务治理、trace 和指标足够稳定后，比较以下策略，而不是预设必须升级 `wiki_recall`：

- **A：基础文件工具**：只提供限制在 `wiki/` 范围内的只读 `list_files + search + read_file`，由 Agent 自主查看索引、换关键词、定位和分页阅读。
- **B：当前专用工具**：只提供现有 `wiki_recall`。
- **C：BM25 专用工具**：仅当 B 已证明专用召回有价值、但失败主要来自排序质量时，才实现“精确实体规则 + 标题/分类/正文 chunk BM25”。

实验要求：

1. 固定 Wiki fixture 与查询集，覆盖公司名/股票代码精确查询、不知道文件位置、多关键词与同义改写、相似干扰页、正文深处信息、跨页面综合和无答案场景。
2. 三组使用相同模型、fixture、最终任务、步骤/Token/成本预算和 outcome grader；不要求固定工具调用路径。
3. 以环境最终答案为主要验收，比较成功率、无依据作答率、步骤、Token、延迟和上下文字符数；同时用 trace 解释目标页面是否被发现/读取，B/C 额外记录 Recall@K 与 MRR。
4. 如果 A 的正确率和稳定性持平或更好且成本可接受，删除 `wiki_recall`；如果 B 明显提高成功率、稳定性或效率，保留专用工具；只有 B 有价值但排序不足时才进入 C。
5. 如果 BM25 后失败仍主要来自没有词汇重叠的同义改写，再评估 embedding 或混合检索，不提前引入向量基础设施。

若实现索引，它属于派生产物，不写入 `raw/`；需记录源页面 hash/mtime，并提供确定性重建和过期检测。该实验当前只登记，不主动实施。

### 验收

- 现有业务测试不回退。
- Lucas 的一次真实执行可以生成同 schema 的 trace；replay 只消费允许保留的脱敏字段。
- 通用 Harness 不 import 投研业务模块。
- 业务 adapter 可以自行注册工具、context provider 和 validator。
- 被实验否定的机制不因产品已有类似代码而强行接入。

## 8. 建议目录结构

```text
harness/
  __init__.py
  models.py
  runner.py
  budgets.py
  trace.py
  model_adapter.py
  environment.py
  tools/
    base.py
    registry.py
    generic/
      filesystem.py
      web_search.py
    business/
      stock.py
      wiki.py
    process.py
    mcp.py
  policies/             # 到对应实验再增加
    planner.py
    validator.py
    context.py

prompts/harness/
  planner.md
  validator.md
  context-summary.md

evals/
  harness/
    cli.py
    models.py
    runner.py
    workspace.py
    grader.py
    report.py
    replay.py
    adapters/
  suites/
    smoke.yaml
    business-capability.yaml
  tasks/
  experiments/

runs/                 # gitignore，仅本地实验产物
  <run_id>/
    manifest.json
    trace.jsonl
    result.json
    metrics.json
    artifacts/
    replay.html

docs/harness/
  experiment-log.md
  trace-schema.md
  tool-contract.md
  benchmark-guide.md
```

目录表示职责边界，不要求一次创建全部文件。Phase 0 只创建 Eval MVP 与最小 Runner 真正使用的部分。

## 9. “干中学”执行节奏

每个 Phase 建议按同一节奏完成：

### Step A：提出假设

例：显式 planner 会提高多步骤代码任务成功率，但增加简单任务成本。

### Step B：先写失败任务

增加 2—4 个当前 baseline 容易失败、但能自动验收的任务。

### Step C：实现最小机制

只实现让这些任务可验证的最小版本，不预先抽象未来 Provider、数据库或分布式执行。

### Step D：跑实验

至少运行 baseline 与新 variant，并保存所有 trace。

### Step E：失败复盘

把失败归因到有限分类：

```text
planning
context
tool_selection
tool_execution
validation
recovery
model
grader
infrastructure
```

### Step F：记录学习结论

每阶段必须在 `docs/harness/experiment-log.md` 记录：

- 原始假设。
- 实现了什么。
- 指标变化。
- 代表性成功/失败 replay。
- 哪些设计判断被证伪。
- 下一阶段要保留、删除或修改什么。

没有实验结论的 Phase 不算完成。

## 10. 里程碑建议

不绑定自然周，以可验证里程碑推进：

| Milestone | 包含阶段 | 完成标志 |
|---|---|---|
| M1 可信 Baseline | Phase 0 | smoke/business 分层、隔离运行、可靠性地板、versioned trace、首份成绩单 |
| M2 Tool Runtime | Phase 1 | 结构化工具协议、三种输出视图、权限和故障测试 |
| M3 Planner 实验 | Phase 2 | baseline vs planner 的可归因结论 |
| M4 自修正实验 | Phase 3 | Validator/Revision 与四类恢复指标 |
| M5 Context + MCP | Phase 4—5 | 通过门控的 context selection/compression 与一个 MCP 对照实验 |
| M6 Eval Lab | Phase 6—7 | suite 治理、稳定 trace schema、按需 HTML replay |
| M7 连续实验 | Phase 8—9 | 逐项消融结论和产品中受控应用 |

## 11. 风险与控制

### 11.1 过早框架化

风险：大量时间花在接口、插件和配置系统，固定任务成功率没有变化。

控制：一个抽象至少服务两个真实调用方再提取；每阶段限制新增核心对象数量。

### 11.2 Benchmark 过拟合

风险：prompt 针对固定任务背答案。

控制：公开任务结构，隐藏部分 expected value；同类任务保留未调试 holdout fixture。

### 11.3 LLM 非确定性

风险：少量 runs 得出错误结论。

控制：每个配置至少 3 次运行，报告分布和失败样本，不只报告单次结果。

### 11.4 Validator 自我欺骗

风险：LLM validator 认为成功，但真实产物不合格。

控制：benchmark grader 是最终裁判；记录 validator-pass/grader-fail 指标。

### 11.5 Retry 放大成本

风险：错误被反复重试，latency 和 cost 激增。

控制：区分 provider retry、tool retry、model correction 和 revision；只对明确 transient provider error 或安全的幂等工具自动重试，分别记录恢复率并设置独立预算。

### 11.6 Trace 泄露敏感信息

风险：prompt、环境变量、文件内容进入 replay。

控制：统一 redaction、环境变量白名单、artifact 分离、仅使用虚构 benchmark 数据。

### 11.7 Harness 与 Lucas 再次耦合

风险：通用 Runner 被业务字段污染。

控制：业务能力通过 adapter 注册；Harness 的核心模型不得出现公司、行业、报告等业务概念。

## 12. 第一轮最小切片

为了尽快获得第一次完整学习反馈，建议第一轮只做：

1. 严格、versioned `TaskSpec/RunLimits/AgentResult/GradeResult`。
2. 临时工作区、Oracle/reference、Outcome/Safety/Process grader。
3. 共用的最小 AgentRunner、ModelAdapter、StepContext、Environment/ToolRuntime 和 TraceSink。
4. `read_file/search_code/apply_patch/run_tests` 四个工具。
5. max model turns/corrections、run/model/tool timeout、cancellation、输出上限和清理。
6. versioned JSONL trace：model、tool、error、artifact、finish。
7. deterministic FakeModel loop integration test。
8. 6 个 smoke tasks，各运行 3 次并生成第一份 baseline。

这轮刻意不做 Planner、Validator、compression、MCP 和 HTML replay。成功标准是能够可信回答：

> 当前最小 single Agent 在哪些原子能力上成功或失败，失败来自 Agent、工具、grader 还是基础设施？

smoke baseline 冻结后，再加入业务 capability；两层 baseline 都可信后才进入 Planner 实验。

## 13. Definition of Done

整个路线图不是以“所有模块都有代码”为完成，而以以下证据为完成：

- 所有进入 smoke、capability、regression、holdout 的任务都通过 `validate-task`，可在干净环境运行。
- baseline 与实验保留的 variants 可通过配置组合同一个 Runner。
- 每个 run 都有 manifest、trace、metrics 和 artifact，并能按需生成 replay。
- baseline 的 model/tool loop 可从 trace 还原；Plan/Validation/Revision 只在相应 variant 中出现。
- timeout、cancellation、四类 retry/correction/revision、max steps 和工具恢复都有注入测试。
- Context 超预算时发生一次可追踪压缩。
- 至少一个 MCP Server 被实际用于 benchmark。
- 每个进入下一阶段的机制都有至少 3 trials/task 的成对对比报告，并根据方差增加 trial。
- 有代表性成功与失败 replay。
- 有明确记录哪些机制改善成功率，哪些只增加成本。
- Lucas 产品 single path 与 Eval Adapter 复用同一 AgentRunner、ToolRuntime 和 TraceRecorder。

达到这些标准后，Lucas 才真正从“带工具的固定工作流”进化为一个可以持续实验、测量和复盘的 Agent Harness。

# M3 Planner 实验：实现报告

> 2026-07-25 · Phase 2（Planner 单变量实验）

## 1. 设计决策

### 为什么选 Codex 式哑工具方案

路线图给了三条路径：重 Planner（结构化 plan schema）、Codex 式（哑工具 + 模型自律）、
Thought 字段（每步推理）。选择 Codex 式的核心理由：

- **实现成本最低**：不加新 Runner 状态、不改核心循环，`update_plan` 就是一个普通业务工具
- **可渐进升级**：如果哑工具不够用，再升级为重 Planner；如果够用，保持简单
- **工业验证**：Codex CLI 的生产实践证明了「工具 + prompt + 模型自律」在多数场景足够

哑工具的代价是**低可靠性**——plan 只是上下文中的一段文字，模型随时可以忽略或不更新。
这个代价在实验阶段可接受，而且正好通过 eval 来测量。

### 最终行为范式

经过真实运行和迭代，确定的范式是「**侦查 → 规划 → 执行**」三段式：

```
侦察（1-3 步）：快速搜索了解情况
规划（1 步）：update_plan 制定步骤
执行（N 步）：按计划逐步操作，每阶段更新计划状态
回答（1 步）：最终 answer
```

没有强制「第一步必须是 plan」。行为约束通过 prompt 而非代码实施，
把执行策略的选择权留给模型。

---

## 2. 实现架构

```
harness/tools/generic/planning.py     ← update_plan 哑工具
    │
    ├── ToolRuntime 注册
    │   ├── server/services/agent_stream.py   ← 聊天路径 + SSE plan_update 事件
    │   └── evals/harness/adapters/lucas_single.py  ← eval 路径
    │
    ├── SSE plan_update 事件 → web/src/hooks/useChat.ts → PlanCard 组件
    │
    └── prompts/
        ├── agent-loop.md             ← 循环规则（plan 的使用方式和约束）
        └── lucas-system-prompt.md    ← 系统级引导（操作顺序、最终回答）
```

### 哑工具设计要点

- `update_plan` 接收 `steps` 列表（也宽容接受 `plan` 字段、字符串自动转换）
- 回显 emoji 格式化的计划全文到 observation（Runner 只回放 observation，不回放 assistant 消息）
- Harness 不保存 plan 状态、不校验状态机、不强制执行——计划完全由模型自律维护

### 前端 PlanCard

- Todo-List 风格，indigo 色调
- 状态图标：⬜ pending / 🔵 in_progress / ✅ completed
- 实时响应 SSE `plan_update` 事件更新

---

## 3. Eval 设计

### 任务

| 任务 | 场景 | 工具 | 验收方式 |
|---|---|---|---|
| MULTI-01 | 跨文件数据汇总（4 份季度报告 + 干扰文件） | list_files, read_file, search, update_plan | answer_json 检查汇总值 |
| MULTI-02 | Wiki 多公司调研对比（3 家激光雷达公司，各 ~2000 字档案） | wiki_recall, read_file, write_file, update_plan | file_content 检查报告文件存在且包含关键公司名 |
| READ-02 | 38 万字招股书导航定位 | read_file, update_plan | answer_json 检查表格数据 |
| LOOP-01 | Wiki 不存在公司时的兜底行为 | wiki_recall, update_plan | 验证护栏收束 |

### plan_usage grader

- 统计 trace 中 `tool_call_started` 事件里 `tool == "update_plan"` 的次数
- 支持 `min_calls` / `max_calls` 上下界
- 设为 `required: false`：作为对比指标而非硬闸门，不因 Oracle 验证而阻塞

### 实验对照

```
planner-experiment-v1
├── Baseline（当前 agent-loop.md，不强制 plan）
├── +Planner（当前 agent-loop.md，工具已就绪）
└── 对照指标：success rate / steps / plan_usage 调用次数 / tokens / latency
```

---

## 4. 设计迭代：碰到的问题

以下只记录与核心设计思想相关的问题，纯代码 Bug（字段放错位置、配置遗漏等）不在此列。

### 问题 1：工具契约 vs 模型训练记忆

**现象**：模型调用 `update_plan` 时传 `{"plan": "..."}` 而不是 `{"steps": [...]}`。

**原因**：Codex 的 `update_plan` 用 `plan` 参数，模型在训练数据中见过大量此类调用，
凭记忆用了 Codex 的参数名。

**解决**：工具改为同时接受 `plan` 和 `steps` 两种字段名，`plan` 为字符串时自动转为单步。
这反映一个设计原则：**工具契约应该宽容模型的训练偏差，在参数名层面做兼容，而不是
通过 prompt 反复纠正**。

### 问题 2：工具操作完成 ≠ 任务完成

**现象**：Agent 执行了 13 步工具调用（搜索、写入 6 个文件、更新索引），但没有输出
最终回答，trace 以 `step_finished` 结束而非 `done`。

**原因**：模型把「写完文件」当成了任务完成的标志。但用户需要的是一个明确的回答
来确认任务确实完成了——工具操作是过程，answer 是交付物。

**解决**：在 prompt 中新增独立章节「完成后的最终回答」，明确要求：
- 总结做了什么
- 关键发现和结论
- 哪些结果落盘到了哪些路径
- 「不要默默地完成工具调用就停止」

**启示**：Agent 协议中 `action: answer` 的语义是「这是最终交付物」，而不只是「我一句
话总结一下」。这个区分需要在 prompt 中反复强调。

### 问题 3：Plan 的僵死——制定了但不维护

**现象**：Agent 在 Step 1 和 Step 4 各更新了一次 plan，之后 9 次工具调用都没有再更新。
前端 PlanCard 显示的计划状态在 Step 4 之后就僵住了。

**原因**：模型制定计划后进入了「执行模式」，注意力集中在当前步骤，忘记了维护 plan
的展示状态。

**解决**：在 prompt 中加「每完成一个阶段就更新计划」——用完一个工具、完成一批文件
写入、或一个调研阶段结束时，立即调用 `update_plan` 标记 completed/in_progress。
把「维护 plan」和「完成阶段」绑定为同一个动作。

**启示**：哑工具方案中，plan 的维护完全依赖模型自觉。如果后续实验仍然出现僵死，
考虑让 Runner 在每个 step 末尾自动回显当前 plan（增加上下文权重），或切换到
重 Planner（代码强制状态更新）。

### 问题 4：操作顺序——模型不自动推导依赖关系

**现象**：Agent 先写入了行业对比报告（Step 9），然后才开始写公司档案（Step 10-11）。
报告写在了数据收集之前。

**原因**：在单步 JSON 协议下，模型每一步只看到当前状态，没有全局执行顺序的概念。
它不知道「对比报告依赖公司档案」，把这个选择当成了自由排序。

**解决**：在 prompt 中加了明确的操作顺序脚手架：
- 先收集再产出
- 先写公司档案再写行业对比报告
- 修改文件前先读取（read_file → apply_patch，不要直接 write_file 覆盖）

**启示**：LLM 不会自动推导领域内的依赖关系。Agent Harness 的价值之一就是把
「领域执行知识」编码进 prompt。等 Phase 3（Validator），这类操作顺序约束
可以由代码而非 prompt 保证。

### 问题 5：重复成功——比重复失败更隐蔽

**现象**：Agent 搜了中际旭创拿到信息，继续做了其他事，然后又回来搜了一次中际旭创。
不是上次失败了——是忘了已经搜过了。

**原因**：原有规则只覆盖「不要重复失败的调用」，没有覆盖「不要重复成功的调用」。
在 20+ 步的长程任务中，早期 observation 在 prompt 中的权重随新 observation 累积
而稀释，模型倾向于重新验证。

**解决**：加规则「不要重复成功的搜索：如果已用相同或高度相似的查询词获得了有效
结果，不要再次搜索」。

**启示**：这本质上是 Phase 4（Context 管理）要解决的问题——通过 Context selection
把关键 observation 保留在注意力窗口内，避免模型「忘记」。当前的 prompt 级规则只是
临时缓解。

### 问题 6：plan-first vs 模型自然行为

**现象**：Agent 的第一步是 `web_search` 而非 `update_plan`。即使 prompt 明确写了
「复杂任务第一步必须是 update_plan」，仍然不生效。

**原因**：模型的自然行为是「先摸清情况再制定计划」，而非「先制定计划再动手」。
强行在 prompt 中约束第一步必须 plan，是在框死模型更优的执行策略。

**解决**：撤销强制规则，改为「允许先做 1-3 步侦查，再调用 update_plan 制定正式计划」。
确认了最终范式是「侦查 → 规划 → 执行」三段式。

**启示**：prompt 的设计方向应该是**放大模型的已有能力**，而不是纠正模型的自然倾向。
当 prompt 规则和模型行为持续冲突时，退一步考虑：是不是规则本身有问题？

---

## 5. 当前状态与下一步

- **基础设施就绪**：工具、SSE、前端、eval 任务、grader 全部可用
- **prompt 稳定**：经过 2 轮迭代，规则集不再大幅变动
- **eval 待运行**：planner-experiment 套件需要在真实模型上跑 baseline vs planner 对照
- **关键指标**：success rate / steps / plan_usage 调用次数 / 简单 vs 复杂任务分层报告

下一步：运行 `planner-experiment-v1` 套件各 3 trials，记录对照结论——
哑工具 Planner 是否显著改善多步骤任务的成功率和步效率。

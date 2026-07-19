# Experiment Log

按路线图"干中学"节奏 Step F 记录：每次实验的假设、实现、指标变化、代表性 replay、被证伪的判断、下一阶段决策。

---

## 2026-07-19/20：Harness Phase 0 落地与首轮机制修复

### 背景

本轮把 Eval Harness 从"只有 2 个 smoke 任务和 Oracle 自验"推进到"真实模型（lucas-single）可运行、trace 可复盘、失败可归因"的状态，并完成了第一次完整的"trace 复盘 → 机制修复 → 对照验证"循环。

### 一、已完成的建设

**共享 Agent 运行时（harness/）**

- `AgentRunner` 最小循环（model → tool → observation → model），产品与 Eval 共用
- 工具集：read_file（offset/max_chars）、list_files、search、apply_patch（唯一替换）、write_file（默认拒绝覆盖）
- `evals/harness/adapters/lucas_single.py` 接入评估，`run-suite` 支持 suite 批量执行与汇总

**Trace 补全（关键设施）**

- 每步记录 `prompt_rendered` / `model_call_started/finished` / `action_parsed`，完整 prompt 与模型原始输出写入 `artifacts/`，observation 全文内联于 `tool_call_finished`
- 埋点 `observation_chars` / `total_observation_chars`，为 Phase 4 Context 实验记账

**题库（capability-v1，5 题）**

| 任务 | 测量能力 | 累计真实表现 | 状态归因 |
|---|---|---|---|
| READ-02 | 长文导航（只许 read_file） | 修复前 8 trial 约 5 过 3 挂；修复后 3/3 | model（导航策略）→ 已转为 Phase 2 探针 |
| READ-03 | 关键词定位（search） | 稳定通过（1 步命中） | — |
| LIST-01 | 工作区盘点 | 6+ trial 错 2 | model（"其中"指代理解偏差，已确诊） |
| EDIT-02 | 歧义编辑（apply_patch） | 稳定通过 | — |
| WRITE-01 | 新建文件（write_file） | 首次即通过 | — |

### 二、代表性实验：READ-02 导航失败与机制修复

**假设**：READ-02（38 万字符招股书定位章节）的失败来自模型导航策略。

**失败复盘（trace 证据）**

1. 第一次失败：12 次跳读中 4 次重读开头区域；形成正确夹逼区间后探测点全部落在区间外。归因：状态追踪缺陷
2. 第二次失败：模型第 5 步就输出了**完全正确的答案**，但用了裸 JSON（无 `{"action":"answer"}` 外壳），被判 invalid；且 invalid 反馈文案"不是合法 JSON"事实上错误，模型连续 3 次原样重发。归因：**机制缺陷**，不是模型问题

**机制修复**

- `_parse_action` 增加 fallback：无 action 外壳的 JSON 对象按 answer 接受
- invalid 反馈文案改为明确说明两种外壳格式

**对照结果**：修复后 READ-02 3/3 通过，且轨迹质量显著改善（零 invalid、零重读开头，出现三种有效策略：直接夹逼 6 步 / 地图式粗扫 8 步 / 线性+跳跃 10 步）。

**结论**：保留修复。失败复盘证明"答案对、格式错"属于 harness 宽容度问题，不应计入模型失败。

### 三、出题修正：READ-02 改题

原题（三个专利数字）存在捷径：数字在招股书前段概要也出现过，模型不走目标章节也能答对。改为"研发人员情况"表格的四年人数（其中 2,891 和 2,606 全文仅出现一次），捷径被堵死。

**出题原则（沉淀）**：

- 预期答案的关键事实应**全文唯一**或仅在目标位置可得，出题时用 grep 验证出现次数
- 要测策略能力，fixture 需包含可利用的元信息（目录/索引），让"会规划的模型"能跑赢"线性执行的模型"

### 四、被证伪或修正的判断

1. ~~"READ-02 改善是因为 read_file max_chars 调大"~~ —— 证伪。Runner 存在 4000 字符二次截断，模型实际看到的页面没变。教训：**trace 不完善时的归因不可信**；机制改动后必须确认真实生效路径再下结论
2. ~~"LIST-01 失败原因待查"~~ —— 通过补全的 trace 确诊：模型把"其中最大的文件"理解为所有文件而非 yaml 文件，信息获取无缺陷，纯理解偏差。归因 model 类，留待 Validator 实验
3. ~~"模型不会利用目录跳读可能是机制问题"~~ —— 部分证实部分搁置：修复协议缺陷后模型展现了三种有效导航策略；但"预算可见/策略提示"两个 prompt 层面的改进**决定不做**，保持 READ-02 作为裸能力探针

### 五、当前 baseline 固定项（供未来对照）

- 模型：providers.yaml 默认（DeepSeek），temperature=0
- prompt：`prompts/harness/tool-loop.md`（无预算提示、无导航策略提示）
- READ-02：max_steps=12，allowed_tools=[read_file]，read_file 默认 max_chars=16000
- 成功率参考（小样本）：READ-02 修复后 3/3；LIST-01 约 4/6；其余 3 题稳定通过

### 六、下一阶段决策

- **READ-02 登记为 Phase 2（Planner）导航能力探针**，不做任何调优。假设：结构化状态/显式规划能提升长文导航的成功率和效率（当前 prompt 消耗 8.5 万-19.3 万字符/run）
- **LIST-01 登记为 Phase 3（Validator）候选驱动案例**："答案是否回应题目约束"的校验有望拦截指代错误
- **READ-03 / EDIT-02 / WRITE-01 稳定通过**，攒满 3+ trials 后可迁入 regression suite
- 已知粗糙项（不阻塞）：trials 样本小；上下文无预算（Phase 4 实验变量）；run-suite 跑全套超 5 分钟需分批（需要时再加 --tasks 过滤）

### 七、产物位置

- runs：`runs/<suite>-<时间戳>-<hash>/runs/<task>-<hash>/`（manifest / trace.jsonl / result.json / artifacts/ / workspace/）
- 代表性 replay：修复前失败 `runs/tmp-read02-20260720-000317-aae0dde6/runs/read-02-fed6c05c7623`；修复后成功 ×3 `runs/tmp-read02-20260720-003325-96570d18/runs/`

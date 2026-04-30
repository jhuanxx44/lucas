# Lucas Agent 工作流迭代优化方案

## 背景

当前 Lucas 的多 Agent 机制是：Manager 根据问题分派多个研究员，研究员并行输出，最后由 synthesis 汇总。

这种设计实现简单、覆盖面广，但有两个结构性问题：

1. 多 Agent 容易变成“多个角度写作文”。不同研究员各自生成一段分析，最后汇总更像观点拼接，不天然提升正确性。
2. 验证发生得太晚。当前验证主要在研究员输出完成后执行，只能发现部分 URL 和数字问题，不能阻止错误材料进入推理和 synthesis。

这两个问题应该合并处理，但不能用“大拆 Agent”的方式一口气解决。更稳的方向是：保留现有主流程，在其前后逐步补上 evidence 和 claim 两个结构化层，让系统先获得可追溯能力，再决定哪些职责值得升级成独立 Agent。

## 核心判断

目标架构可以承认“检索、证据抽取、核验、分析、反方、综合”这些职责，但代码实现不应该一开始就拆成六个 Agent。

第一阶段应遵守三个约束：

- 默认不要新增 Agent。
- 能用普通 service/function 做的，不用 Agent。
- 只有当某个职责需要独立 prompt、独立状态、独立失败恢复时，才升级为 Agent。

否则系统会从“可理解的多研究员流程”变成“流程很多但每步都不够稳定的复杂系统”，维护成本会上升，收益反而不确定。

## 目标

本轮迭代的目标不是让 Agent 更多，而是让研究过程更可靠。

成功标准：

- 最终报告旁边有结构化 `evidence.json` 和 `claims.json`。
- 每个关键 claim 尽量能追溯到 evidence id。
- 没有 evidence 的 claim 被标记为低置信或未验证。
- 验证逻辑逐步从“报告生成后检查”前移到“分析前先整理证据”。
- 现有聊天和报告体验不被大幅打断。

## 三层收敛方案

### 1. Evidence Layer

职责：

- 收集 wiki、memory、web search、market data 等上下文。
- 登记来源。
- 抽取关键片段、关键数字、资料时间。
- 做基础 URL 和数字校验。

实现原则：

- 第一阶段优先做成 Python service，不做 Agent。
- 先覆盖已有 `source_urls`、`market_data`、wiki context。
- evidence 抽取可以先粗糙，但格式要稳定。

产物：

```text
evidence.json
```

### 2. Analysis Layer

职责：

- 保留现有研究员机制。
- 研究员仍然可以并行分析，但 prompt 中加入 evidence 引用约束。
- 要求输出或可抽取出核心 claims。

实现原则：

- 不急着拆出产业分析员、公司分析员、反方分析员等新角色。
- 先让现有研究员基于 evidence bundle 工作。
- 反方风险可以先作为研究员或 synthesis prompt 的固定章节，不一定成为独立 Agent。

产物：

```text
claims.json
```

### 3. Synthesis Layer

职责：

- 汇总研究员输出。
- 展示主要结论、证据覆盖、反方风险、置信度。
- 归档 report、evidence、claims。

实现原则：

- synthesis 仍然输出用户可读 Markdown。
- 内部逐步改为消费 claims/evidence，而不是只消费研究员全文。
- wiki 更新暂时保持现状，后续再改为消费 verified claims。

产物：

```text
report.md
meta.json
```

## 最小可维护流程

第一版不要上完整 workflow orchestrator。推荐流程如下：

```text
question
  -> collect_context()
  -> build_evidence_bundle()
  -> run_existing_researchers(evidence_bundle)
  -> extract_claims()
  -> synthesize_with_risks()
  -> persist report + evidence.json + claims.json
```

这条流程只新增两个真实概念：

- `Evidence`
- `Claim`

它能解决最核心的问题：结论有证据、报告可追溯、验证可以逐步前移，同时不会把系统复杂度推高到难维护。

## 建议的数据结构

### Evidence

```python
@dataclass
class Evidence:
    id: str
    source_id: str
    kind: str  # source | snippet | metric | historical_conclusion
    subject: str
    text: str
    path_or_url: str = ""
    snippet: str = ""
    value: float | None = None
    unit: str = ""
    as_of: str = ""
    reliability: str = "medium"
    verification_status: str = "unverified"
    issues: list[str] = field(default_factory=list)
```

### Claim

```python
@dataclass
class Claim:
    id: str
    type: str  # fact | interpretation | forecast | risk | assumption
    text: str
    evidence_ids: list[str]
    confidence: str = "medium"
    assumptions: list[str] = field(default_factory=list)
```

第一版不要引入更多对象。`Challenge`、`ResearchWorkflowResult`、`KnowledgeEvent` 可以等需求明确后再加。

## 分阶段迭代方案

### Phase 1：sidecar 先行，不改主流程

目标：建立可追溯格式，不干扰现有体验。

改动范围：

- 新增 `Evidence`、`Claim` 数据结构。
- 报告归档时额外保存 `evidence.json` 和 `claims.json`。
- evidence 先从已有 `source_urls`、`market_data`、wiki context 中生成。
- claim 可以先从 synthesis 或研究员输出中抽取。

验证方式：

- 每次新报告目录下都有 sidecar。
- 核心结论至少部分能关联 evidence。
- 无 evidence 的 claim 标记为 `unverified` 或 `low`。

取舍：

- 这一阶段验证仍然偏后置。
- 但它最小化风险，先让系统拥有稳定结构。

### Phase 2：把验证前移到 evidence

目标：让 URL、数字、时效检查作用在 evidence 上，而不是只检查最终报告。

改动范围：

- 新增 `verify_evidence`，复用现有 URL 和财务数据校验逻辑。
- evidence 增加 `verification_status` 和 `issues`。
- prompt 中明确提示研究员优先使用 verified evidence。

验证方式：

- 不可达 URL 或明显错误数字能在 evidence 中被标记。
- synthesis 能显示“未验证证据”或“低置信证据”的影响。

取舍：

- 不要求第一版禁止使用所有 unverified evidence。
- 先标记，再逐步收紧约束。

### Phase 3：让研究员显式引用 evidence id

目标：把“证据先行”真正接入分析过程。

改动范围：

- `run_existing_researchers` 的 prompt 增加 evidence bundle。
- 要求关键判断用 evidence id 标注。
- `extract_claims` 优先读取研究员显式标注的 evidence id。

验证方式：

- 研究员输出中能看到 evidence id。
- `claims.json` 中大部分 claim 有 `evidence_ids`。

取舍：

- 允许部分观点类 claim 暂时没有 evidence，但必须标为低置信或假设。

### Phase 4：再考虑是否新增流程型 Agent

目标：只在确有收益时升级复杂度。

升级为独立 Agent 的条件：

- 这个职责需要独立 prompt，且 prompt 明显不同于现有研究员。
- 这个职责失败时应该单独恢复，而不是拖垮整个研究。
- 这个职责有独立结构化产物。
- 这个职责在多次使用中被证明稳定且高价值。

可能升级项：

- `Contrarian Agent`：当反方风险章节稳定有价值时再拆。
- `Verifier Agent`：只有规则校验不够，需要模型判断来源冲突时再拆。
- `Retrieval Agent`：只有检索计划明显需要 LLM 参与时再拆。

不建议第一阶段新增：

- 独立 Portfolio Manager Agent。
- 独立 Domain Analyst Agent。
- 完整 workflow orchestrator。
- 复杂数据库或向量库以外的多层状态系统。

### Phase 5：wiki 更新消费 verified claims

目标：减少 LLM 直接根据整篇 synthesis 改 wiki 的风险。

改动范围：

- wiki update plan 后续基于 `claims.json`。
- verified/high-confidence claim 才能进入公司或行业档案。
- medium/low confidence claim 保留在报告，不直接进入长期 wiki。

验证方式：

- wiki 新增内容能追溯到 claim id 和 evidence id。
- unverified claim 不会进入长期 wiki 页面。

这一阶段可以晚一点做。前面 sidecar 和 evidence 引用稳定后，再改 wiki 更稳。

## 与现有代码的映射

当前代码可以这样小步演进：

- `agents/models.py`
  - 新增 `Evidence`、`Claim`。

- `agents/research_service.py`
  - 保留现有 `run`。
  - 在调用研究员前构建 evidence bundle。
  - 暂时不要新增完整 `run_evidence_first`，除非 Phase 3 后确实需要。

- `agents/researcher.py`
  - `_build_prompt` 增加 evidence bundle 输入。
  - 逐步减少直接塞大段搜索结果的比例。

- `utils/verify.py`
  - 保留 `verify_result`。
  - 新增 `verify_evidence`。

- `agents/knowledge_service.py`
  - `archive` 写入 `evidence.json` 和 `claims.json`。
  - `update_wiki` 暂时不动，等 claims 稳定后再调整。

- `prompts/`
  - 新增 `claim-extract.md`，`llm-weight: medium`。
  - 视情况新增 `evidence-extract.md`，`llm-weight: medium`。
  - 暂不新增 `contrarian.md` 和 `evidence-synthesis.md`，先在现有 synthesis prompt 中加入反方和证据覆盖要求。

## UI 展示建议

第一阶段前端不需要大改。报告中可以先展示：

- 关键结论数量。
- 有证据支撑的结论数量。
- 未验证结论数量。
- 主要风险和反方观点。

后续再考虑：

- 点击 claim 展开 evidence。
- evidence 显示来源路径、URL、日期、验证状态。
- 报告顶部展示整体证据覆盖率。

## 风险与取舍

### 复杂度失控

这是最大的风险。解决方式是明确升级门槛：没有独立产物、独立失败恢复、独立 prompt 价值的职责，不拆成 Agent。

### sidecar 早期质量不稳定

第一版不追求完美覆盖。只要求核心 claim 能部分关联 evidence，格式稳定比覆盖率更重要。

### prompt 和 schema 漂移

需要代码层校验 JSON。LLM 输出失败时不阻塞主报告，但要标记 sidecar 缺失或不完整。

### 响应时间变长

Phase 1 基本不影响响应时间。Phase 2 和 Phase 3 会增加一些处理成本，但仍比完整多 Agent workflow 可控。

## 推荐实施顺序

1. 新增 `Evidence` / `Claim` 数据结构。
2. 报告归档时写入 `evidence.json` 和 `claims.json`。
3. 新增 `claim-extract.md`，从现有输出抽取 claims。
4. 从已有 `source_urls`、`market_data`、wiki context 构建 evidence bundle。
5. 新增 `verify_evidence`，把验证结果写入 evidence。
6. 让研究员 prompt 引用 evidence bundle。
7. 要求研究员关键判断标注 evidence id。
8. 在 synthesis prompt 中加入反方风险和证据覆盖要求。
9. 等 sidecar 稳定后，再考虑拆独立 Contrarian 或 Retrieval Agent。
10. 最后再让 wiki 更新消费 verified claims。

## 一句话结论

这两个问题应该合并成一条主线，但实现上要克制：先引入 `Evidence` 和 `Claim`，用普通 service 把证据层做起来，再让现有研究员和 synthesis 消费这些结构化产物。

多 Agent 的价值不应该来自“多写几个角度”，而应该来自流程中更可靠的证据、核验、反方和综合。但这些职责不必一开始都变成 Agent，只有被证明稳定且值得独立维护时才升级。

# Responses 原生工具调用迁移实验

日期：2026-07-31
模型：`deepseek-v4-flash`
Endpoint：DeepSeek 官网 `https://api.deepseek.com`
Temperature：0
被测对象：生产 `AgentRunner`、`ResponsesModelAdapter`、`DeepSeekResponsesClient` 与 `ToolRuntime`

## 假设与成功标准

假设：用 Responses 原生 `function_call` / `function_call_output` 取代 Lucas 私有
`action/tool/args/reply` 文本协议，可以删除动作 JSON 解析与流式状态机，减少格式歧义，同时保持固定任务
outcome、安全与 trace 完整性。

主要成功标准：

- 真实 DeepSeek 能完成直接答案、单工具和连续工具任务；
- 原生调用参数经严格 JSON Schema 和本地 `ToolRuntime` 校验；
- 最终答案直接来自 `final_answer` message，不再使用动作 JSON 外壳；
- 固定 eval outcome 不低于迁移前可比结果；
- 步骤、纠正、token、成本和 provider 边界被如实记录；
- 确定性回归、产品 SSE、前端构建和真实 smoke 通过。

本实验没有把上下文压缩、并行工具、server-side conversation state 或 provider fallback 混入迁移，
避免同时改变多个机制。

## 前置能力探针

使用 OpenAI Python SDK 2.38.0 直连 DeepSeek 官网，确认：

| 能力 | 结果 |
|---|---|
| 单 function tool 与 strict JSON Schema | 通过 |
| `function_call_output` 按 provider `call_id` 续接 | 通过 |
| 显式提交上一轮完整 `response.output`，不使用 `previous_response_id` | 通过 |
| Structured JSON output | 通过 |
| reasoning、output text、function arguments 流式事件 | 通过 |
| usage 与 reasoning token details | 通过 |
| `parallel_tool_calls=False` | 请求可接受，但不能保证只返回一个 call |
| thinking 模式下 `tool_choice="required"` | HTTP 400，不支持 |

因此生产请求使用 `tool_choice="auto"` 和 `parallel_tool_calls=False`，但单工具决策继续由 Runner 校验。

## 迁移前 baseline

迁移前的私有 JSON loop 使用相同模型别名、temperature、工具、fixture 和预算：

| Task | Outcome | Steps | Tools | Corrections | Tokens | Wall | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| LOOP-01 | pass | 2 | 1 | 0 | 5,337 | 5.88s | $0.016534 |
| PLAN-01 | pass | 14 | 12 | 1 次空/非法输出恢复 | 68,197 | 87.94s | $0.249934 |

迁移前最近一次 PLAN-01～04 Flash 运行的语义 outcome 为 3/4；PLAN-02 因具体来源/交付不完整失败。
该历史运行每题只有 1 trial，只作为扩展 suite 的方向性对照。

## 最终实现的重复 trials

最终代码对 LOOP-01 和 PLAN-01 各运行 3 次真实 trial。三个 PLAN-01 trial 都在修正 fixture 的一处
依赖方向笔误后运行；grader、工具、预算和期望环境状态没有改变。

### LOOP-01

| Trial | Outcome | Steps | Tools | Corrections | Tokens | Wall | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| `loop-01-e3061b129e6a` | pass | 2 | 1 | 0 | 5,476 | 3.46s | $0.013142 |
| `loop-01-512137acfee6` | pass | 3 | 2 | 0 | 8,948 | 5.56s | $0.022236 |
| `loop-01-e9b35e3cb28e` | pass | 2 | 1 | 0 | 5,579 | 2.73s | $0.012958 |
| **平均** | **3/3** | **2.33** | **1.33** | **0** | **6,668** | **3.92s** | **$0.016112** |

相对单次 baseline，平均 steps +16.7%、tokens +24.9%、cost -2.6%、wall -33.4%。样本量只有三次，
延迟和成本差异不应外推；关键结论是 outcome、裸 JSON 答案和停滞护栏均稳定通过。

### PLAN-01

| Trial | Outcome | Steps | Tools | Corrections | Tokens | Wall | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| `plan-01-d4d354f355eb` | pass | 19 | 17 | 1 | 147,727 | 65.98s | $0.378344 |
| `plan-01-3ad4f0397b6b` | pass | 20 | 17 | 2 | 148,067 | 56.71s | $0.368594 |
| `plan-01-0212930d5f3d` | pass | 18 | 16 | 1 | 118,783 | 46.79s | $0.295106 |
| **平均** | **3/3** | **19.0** | **16.67** | **1.33** | **138,192** | **56.49s** | **$0.347348** |

相对单次 baseline，平均 steps +35.7%、tokens +102.6%、cost +39.0%，wall -35.8%。三次都完成三个
服务配置、rollout 文档、最终回答和全部 grader，但每次仍有 1～2 次“一个响应返回多个 function call”
纠正。这证明 outcome 已恢复，也暴露了 DeepSeek 对单工具约束的稳定兼容边界。

## PLAN-02～04 覆盖结果

最终实现另对其余复杂任务各运行 1 次：

| Task | Outcome / Safety / Process | Steps | Tools | Corrections | Tokens | Cost | 结论 |
|---|---|---:|---:|---:|---:|---:|---|
| PLAN-02 | fail / pass / fail | 24 | 23 | 1 | 144,629 | $0.334418 | max_steps；只完成部分公司页，未生成报告/索引 |
| PLAN-03 | pass / pass / pass | 18 | 16 | 1 | 117,981 | $0.291262 | 全部通过 |
| PLAN-04 | pass / pass / pass | 25 | 23 | 1 | 320,288 | $0.829026 | 全部通过 |

最终 PLAN-01～04 为 3/4，失败题仍是 PLAN-02，与最近可比的旧 loop 语义 outcome 相同。由于每题只有
一次扩展 trial，不能声称迁移对单题能力没有影响；它只能说明没有观察到 suite outcome 降级，而长任务
token 明显上升。

所有最终重复产物位于 `/tmp/lucas-responses-native-final-trials/`；额外的本地主线成功 trials 位于
`/tmp/lucas-responses-native-post-fix/` 和 `/tmp/lucas-responses-native-post-fix-2/`。

## 迁移中暴露并修复的问题

### 1. commentary 被误当最终答案

DeepSeek 会在单个 function call 旁返回 `message phase=commentary`。SDK 的 `response.output_text` 聚合
了这段文字，初版 Runner 因而把合法工具轮误判为“工具 + 最终文本”混合响应。

修复后，Adapter 按 phase 分离 commentary 和 final answer：commentary 只进入 trace，工具的用户可见
summary 仍来自 strict schema 中的必填参数。最终文本与工具调用真正混合时仍会被拒绝。

### 2. Provider 仍返回多个 function call

初版和最终 trials 都观察到多 call，即使请求已设置 `parallel_tool_calls=False`。Lucas 没有静默执行第一个
调用，也没有并行执行，而是拒绝整个决策并有界纠正。Prompt 同时明确“一次 response.output 最多一个
function_call item”。

这类 correction 在最终 PLAN-01 中没有消失，所以报告把它作为能力边界保留，而不是宣称原生协议已让
所有格式 correction 归零。

### 3. JSON 任务输出了说明文字和 fenced JSON

初版 LOOP-01 语义正确，但最终文本不是裸 JSON，严格 grader 失败。最终 prompt 明确：任务要求 JSON 时
只输出可直接解析的 JSON。Eval adapter 的宽容 `extract_json` 后处理被删除，最终三次均由 grader 直接
解析通过，没有恢复旧动作协议。

### 4. PLAN-01 fixture 自相矛盾

规范原文写成“依赖方先部署”，与 `depends_on`、列出的门槛顺序及 deterministic grader 相反。模型为解决
矛盾读取测试并长时间推理。Fixture 已改为“被依赖方先部署，依赖它的服务后部署”；known-bad 仍失败，
Oracle 仍通过。该改动修复的是实验 ground truth，不是放宽答案。

## Schema、summary 与 trace

最终收集的 9 个真实成功/覆盖 runs 中，116 次已接受的 function call 全部带非空 summary，且同一 run
内没有完全重复的 summary。这里仅说明 schema 强制存在和样本内字符串唯一，不代表人工语言质量已经由
grader 验证。

所有 runs 的 trace 都通过结构完整性检查，并记录：

- 显式 input items 与完整 response items artifact；
- response ID、provider call ID 和 function call output；
- reasoning、commentary、summary、tool result 与 final answer；
- usage、延迟、model correction、deadline/budget/finish reason。

没有观察到 tool schema validation error、tool retry 或 provider retry。多 call 都被归类为 model correction。

## 确定性与产品验证

- 后端非 live 全量测试：283 passed（含迁移发布审查新增回归）；
- 原生 phase/Runner/prompt/eval 聚焦测试：118 passed；
- 前端 changed-file ESLint：通过；
- 前端 `CI=1 npm run build`：通过；
- 真实生产 Runner smoke：读取 `lucas.yaml` 后正确回答模型为 `deepseek-v4-flash`；
- 真实 structured text smoke：`application/json` 返回 `{"ok": true}`；
- 禁止项扫描、`git diff --check`、`raw/` Git 状态：干净。

发布审查额外修复了最终答案预算漏检、流式 commentary 泄漏、非完整响应误接受、provider retry
不可观测、工具 handler 返回类型越界，以及空白模型配置六个问题。provider retry 现在独立记录，仍不计入
model correction；本次真实 smoke 未触发 retry。

## 结论与决策

1. **保留 Responses 原生迁移。** 私有 action JSON、Chat Completions/Gemini 路径、provider 路由和旧答案
   流式解析器已经删除；直接答案、工具续接、SSE 与 trace 均由原生 item 驱动。
2. **Outcome 达到迁移门槛。** LOOP-01 和 PLAN-01 最终各 3/3；PLAN-01～04 观察到 3/4，与最近可比旧
   loop 的语义 outcome 相同。
3. **不把效率问题掩盖为成功。** PLAN-01 平均 token 约翻倍，PLAN-04 达 320k tokens。主要原因是 Lucas
   每轮显式重传完整 response items，加上 DeepSeek 多 call correction 和逐文件读取。
4. **不在本次顺手加入 compaction。** 上下文选择/压缩会改变另一个 Agent 机制，应使用冻结任务单独做
   baseline、实现和多 trial，而不是用不可复现的隐式 provider state 遮盖成本。
5. **`parallel_tool_calls=False` 不是安全保证。** 单工具串行语义继续由 prompt 引导、Runner 校验和
   ToolRuntime 执行边界共同保证。

## 样本限制与下一步

- Baseline 的迁移专用真实任务各只有 1 trial，final 只有 LOOP/PLAN-01 各 3 trials；不能对百分比差异做
  统计显著性解释。
- Provider 只暴露模型别名，没有可验证的后端版本；跨时间行为差异可能含服务端变化。
- PLAN-02～04 final 各 1 trial，只用于覆盖性回归。
- 下一项最有价值的独立实验是显式上下文选择/压缩：固定 Responses 原生协议、模型、任务和预算，比较
  outcome、tokens、cache 命中、trace 可解释性和恢复能力。

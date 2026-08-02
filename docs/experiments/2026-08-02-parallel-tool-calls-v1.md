# 阶段 1：并行工具调用（Responses `parallel_tool_calls=true`）初步验证

日期：2026-08-02
对照固定项：同一 `AgentRunner`、`deepseek-v4-flash`、temperature=0、固定 prompt/任务/grader；
API 直连 `https://api.deepseek.com`。
说明：初步验证（并行 3 trials + 对照 1 trial）；结论只用于决定机制取舍，非细粒度排序。

## 机制假设

- H1：允许模型单轮返回多个互不依赖的 `function_call` 后，Runner 能正确执行全部调用、
  按 `call_id` 回传全部 `function_call_output`，outcome 不劣化。
- H2：多独立查询任务（如 MULTI-01 读 4 个季度报告）的模型调用轮数下降、延迟下降。
- 风险假设：并行可能诱发冗余重复调用（LOOP-01 类任务需护栏收敛）。

## 实现（最小改动）

- `utils/llm_client.py`：`create()` 新增 `parallel_tool_calls` 参数，默认 `true`（替代固定 `false`）。
- `harness/models.py`：`ModelRequest` 新增 `parallel_tool_calls` 字段。
- `harness/runner.py`：
  - 执行循环从 `function_calls[0]` 改为遍历全部 calls：先广播整批 `tool_start`，
    再 `asyncio.gather` 并发执行，最后按原顺序逐个按 `call_id` 追加
    `function_call_output`；全部执行完才进入下一轮（Responses 要求同批 call 的输出
    一起提交），模型 items 每轮只追加一次。
  - `_decision_error`：取消"多于 1 个 function_call 即拒绝"，改为单轮上限
    `MAX_PARALLEL_TOOL_CALLS=4`，超出仍按协议错误有界纠正。
  - 失败签名检测改为按 tool 记录；同轮重复结果不误判停滞。
- `prompts/harness/agent-loop.md`：允许"互不依赖时可并行、单轮最多 4 个"，依赖调用拆轮。
- `evals/harness/adapters/lucas_single.py`：支持 `LUCAS_PARALLEL_TOOL_CALLS=0` 关闭并行做对照。

## 结果（真实 run）

| 任务 | 档 | trials | 全过 | 每轮调用数 | 步数 | 成本/run |
|---|---|---|---|---|---|---|
| MULTI-01 | parallel on | 3 | 3/3 | [1, 4, 0]（稳定并行 4 读） | 3 | $0.033± |
| MULTI-01 | parallel off* | 1 | 1/1 | [1, 4, 0] | 3 | $0.033 |
| LOOP-01 | parallel on | 3 | 3/3 | [1, 0] 或 [2, 0] | 2 | $0.014 |
| LOOP-01 | parallel off* | 1 | 1/1 | [1, 0] | 2 | $0.013 |

\* `LUCAS_PARALLEL_TOOL_CALLS=0` 只关掉 API 请求里的并行开关；DeepSeek 在该开关关闭时
仍会偶发多 call（与 2026-07-31 迁移实验记录一致），而新 Runner 对多 call 一律正常执行，
因此"off"档实际也走了并行执行路径——它验证的是 API 开关本身无抑制效果，不是旧行为对照。

## 结论

- H1 成立：真实模型稳定输出 4 个并行 `function_call`（MULTI-01 3/3 次），全部执行、
  全部回传、outcome/safety/process grader 全过；无 protocol correction。
- H2 部分成立：MULTI-01 每轮调用数 [1,4,0]，单轮即读完 4 个季度报告；与旧 Runner
  （多 call 拒绝 + 有界纠正）相比消除了"合法多 call 被纠正"的失败模式。
- 风险未显现：LOOP-01（反复检索护栏）3/3 通过，未见并行冗余搜索失控；1 次出现
  并行 2 检索但任务照常收敛。
- 已知边界：本次未做旧行为（拒绝多 call）的同预算严格对照；真实 latency 对比样本小
  （并行 7.8s vs off 9.3s，1 对 1，不具统计意义）。
- 决策：**保留并行工具调用**（默认开启，上限 4）。`parallel_tool_calls` 保留
  `LUCAS_PARALLEL_TOOL_CALLS` 开关供后续消融。

## 真实产物

- 并行 trials：`/tmp/lucas-parallel-eval/on/`、`/tmp/lucas-parallel-eval/on2/`
- 对照：`/tmp/lucas-parallel-eval/off/`

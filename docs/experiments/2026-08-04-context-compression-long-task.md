# Context 压缩长任务对照实验（CTX-01，1 trial/档）

日期：2026-08-04
对照固定项：同一 `AgentRunner`、`deepseek-v4-flash`、temperature=0、固定 prompt/任务/grader；
API 直连 `https://api.deepseek.com/v1`（无代理）。
说明：本报告为初步数据（每档 1 trial）；≥3 trials 矩阵待生产参数定稿前执行。
前序实验：`docs/experiments/2026-08-01-context-compression-v1.md`（结论为「机制保留但 trigger
参数不可用」）。

## 1. 机制假设

2026-08-01 的实验里压缩使 PLAN-01 累计输入 token **反升 23%**，归因是压缩挖空了模型后续
仍需要的文件内容，模型只能重读回来（第 14–18 步重读 5 个 `service.yaml`）。

由此提出假设：**压缩的成败由任务形状决定，不由触发频率决定。**

- **状态外化型**：中间结果随手写入文件，原文抽完即弃 → 压缩丢掉的内容后续不需要，应近乎免费
- **交叉综合型**（PLAN-01）：读完全部输入后要横向比较，早期内容到最后仍要用 → 压缩必然引发重读

预期改善指标：状态外化型任务上累计 prompt_tokens 下降、outcome 不降、重读次数接近 0。

## 2. 方法

### 2.1 新增任务 CTX-01（状态外化型）

12 份尽调备忘录（单篇约 5,300 字符，合计 63,522 字符），逐篇抽取 6 个字段写入
`extracts/<代码>.txt`，最后汇总成评级表。任务指令明确要求「读一篇、立即写出该篇的
extracts 文件，再读下一篇」，使外化成为显然做法。

判卷全确定性：`pytest` 校验 12 份抽取文件字段值 + 汇总表评级；`allowed_diff` 锁定只能改
`extracts/*.txt` 与 `汇总.md`；`allowed_tools` 防越界。评级规则三档均有样本，并含两个边界
（HX-009 毛利率恰为 40.0 取 A；HX-010 为 24.9 落 C）与一个高毛利+高风险样本（HX-004 取 B，
证明风险等级真的参与判定）。

### 2.2 新增指标：重读次数

2026-08-01 的重读行为只能靠人工翻 trace 发现。新增 `scripts/count_context_rereads.py`
从 trace 确定性统计：同一 `(tool, path)` 的第 2 次及以后调用计为重读，`read_file` 带 offset
时按 `(path, offset)` 区分（翻页不算重读）。

### 2.3 窗口按实测峰值反推

不再猜窗口。先跑 `LUCAS_CONTEXT_WINDOW=0` 探针量出 CTX-01 真实单轮输入峰值 **46,323 token**，
再按目标倍率反推：

| 窗口 | 触发线（0.8W） | 峰值/触发线 | 首次触发步 |
|---:|---:|---:|---:|
| 12K | 9,600 | 4.8× | 第 5 步 |
| **20K** | **16,000** | **2.9×** | **第 9 步** |
| 32K | 25,600 | 1.8× | 第 15 步 |

选 20K：压缩确实多次触发，但不至于每两步一次（12K 档 4.8 倍与 2026-08-01 失败的
PLAN-01@12K 形态过于接近，风险是再复现一次「压太狠」而非测出机制价值）。

### 2.4 三臂

| 臂 | 配置 |
|---|---|
| baseline | `LUCAS_CONTEXT_WINDOW=0` |
| level2 | `LUCAS_CONTEXT_WINDOW=20000` |
| level1 | `LUCAS_CONTEXT_WINDOW=20000 LUCAS_COMPRESSION_LEVEL=1` |

全部通过环境变量，未改运行时代码。

## 3. 结果（真实 run，1 trial/档）

| 臂 | 任务 | 通过 | 步数 | 工具调用 | 累计输入 | 峰值 | 压缩 | 重读 |
|---|---|:-:|--:|--:|--:|--:|--:|--:|
| baseline W=0 | CTX-01 | Y | 28 | 28 | 727,688 | 46,323 | 0 | 0 |
| **level2 W=20K** | CTX-01 | **Y** | 18 | 29 | **224,931** | 17,429 | 10 | **0** |
| level1 W=20K | CTX-01 | Y | 30 | 39 | 337,011 | 16,178 | 4 | 0 |
| baseline W=0 | PLAN-01 | Y | 7 | 17 | 43,884 | 10,795 | 0 | 3 |
| level2 W=20K | PLAN-01 | N\* | 8 | 17 | 51,691 | 10,868 | 0 | 3 |
| level1 W=20K | PLAN-01 | Y | 11 | 19 | 92,039 | 13,729 | 0 | 3 |

累计输入 token 相对 baseline：

- CTX-01 level2：**−69.1%**（727,688 → 224,931）
- CTX-01 level1：−53.7%（727,688 → 337,011）
- PLAN-01 level2：+17.8%；level1：+109.7%（**均非压缩所致**，见 4.3）

\* PLAN-01 level2 失败原因是回滚顺序写反 + 未调用 `update_plan`，与压缩无关（该臂压缩 0 次）。

## 4. 归因结论

### 4.1 假设成立：状态外化型任务上压缩净赚且零重读

CTX-01 level2 累计输入降 69.1%，outcome 通过，**重读 0 次**。这是压缩机制首次在真实任务上
净赚。工具序列为干净的 read→write 交替（`read_file(memos/HX-001.md)` →
`write_file(extracts/HX-001.txt)` → 下一篇），10 次压缩全部命中 `drop+summarize` 链，
`degraded=False`，丢弃的都是已外化的早期步骤。

与 2026-08-01 的 PLAN-01@12K（+23%、9 次压缩、重读 5 个文件）对照，**差别不在参数而在任务
形状**——假设的核心预测得到证实。

### 4.2 level 2 的 LLM 摘要值这次调用

level1（纯机械挖空）只降 53.7%，且步数从 18 涨到 30、工具调用从 29 涨到 39。trace 显示
原因明确：level1 在写汇总前**把 12 份 extracts 文件逐个重新读了一遍**（第 27–38 次调用），
而 level2 直接写出汇总。

即被丢弃的信息 level1 只能靠重新读文件恢复，level2 的摘要保留了足够信息让模型继续推进。
注意这不计入「重读」指标（读的是自己写的产物而非同一目标两次），但确实是额外成本。

这是此前从未做过的单变量对照，结论是摘要那次 LLM 调用**划得来**。

### 4.3 PLAN-01 本轮不构成压缩对照

三臂 PLAN-01 峰值均约 10.8–13.7K，低于 20K 窗口的 16K 触发线，**压缩全部 0 次**。因此：

- level2 臂的失败是模型随机性，不是压缩代价；
- level1 臂 +109.7% 来自步数波动（11 vs 7 步），不是压缩代价；
- baseline 的 43,884 token 也**不可与 2026-08-01 报告的 125,671 直接比较**——并行工具调用
  上线后步数显著减少。

要保留 PLAN-01 作为敌对形状的对照，须单独用 12K 档跑（其峰值需高于触发线）。

### 4.4 中文 token 密度实测 0.60，runner 默认值低估 71%

从相邻步 prompt 增量反推（每篇备忘录 5,293 字符）：

| 增量 | tok/char |
|---|---:|
| 10,673 − 7,306 = 3,367 | 0.636 |
| 14,062 − 10,929 = 3,133 | 0.592 |
| 17,446 − 14,319 = 3,127 | 0.591 |
| 44,915 − 41,722 = 3,193 | 0.603 |

实测约 **0.60**，而 `harness/runner.py` 的 `DEFAULT_TOKENS_PER_CHAR = 0.35`（注释称「保守
偏高」）对中文散文实际低估约 71%，意味着压缩触发预估在中文上下文中系统性偏晚。

**未改该常量**：runner 有 `_calibrated_ratio` 动态校准，真实运行时会自我修正；改默认值会
影响其他任务的首次触发时机，属独立变更，需单独对照。

### 4.5 顺带修复：grader 答案泄漏进考场

整理本报告时发现 level2 臂第 3 次调用读了 `tests/test_extracts.py`。该文件位于工作区内
（pytest 必须在工作区运行），而初版内联了全部 12 家公司的期望值——**等于把答案放进考场**。

本轮该 run 仍完整读了 12/12 篇备忘录，结论不受影响，但机制上必须堵住。已改为从 `memos/`
现场解析真值并套用规则（规则.md 本就公开），Agent 读到 grader 只能看到规则、拿不到答案；
具体数值移至工作区外的 `tests/test_ctx_long_task_fixture.py` 钉住，并新增测试断言 grader
源码不含任何公司名与营收数字。

## 5. 决策

- **保留压缩机制**，并首次给出适用条件：**状态外化型长任务上开启，交叉综合型任务上收益为负**。
  这比单一 on/off 判决更可用——它给出的是「什么时候该开」。
- **生产参数暂不改动**（`lucas.yaml` 仍为 1M 窗口、生产不触发）。原因：每档仅 1 trial；且
  20K 是模拟装置，见第 6 节失真项。
- **下一步**（按序）：
  1. 补至 3 trials/档确认稳定性（尤其 level1 vs level2 的步数差异是否稳定复现）；
  2. 补 PLAN-01@12K 敌对对照，把「什么形状该开压缩」钉死；
  3. 依据 1、2 决定生产窗口，或改为按任务形状选择性开启。

## 6. 局限

- **小窗口是模拟装置，不是生产参数。** 两处已知失真：预留输出在 20K 下为 10%（2,000），
  在 1M 下为常数 16,384，有效可用比例不同；单个工具输出相对窗口的占比被放大。因此结论只
  支持方向性判断（机制在何种任务形状上成立），**不能当生产参数直接用**。
- 每档 1 trial，无统计意义；步数与 token 的具体数值会随模型随机性波动。
- PLAN-01 本轮未触发压缩，敌对形状的对照尚缺（见 4.3）。
- CTX-01 是人工构造任务，外化行为由指令明确引导。真实用户提问未必有这么干净的形状。

## 7. 产物与复现

```bash
# 探针（量峰值）
LUCAS_CONTEXT_WINDOW=0 .venv/bin/python -m evals.harness run-suite \
  evals/suites/context-long-task-experiment.yaml --agent lucas-single --trials 1 --runs-root runs

# level2 / level1
LUCAS_CONTEXT_WINDOW=20000 .venv/bin/python -m evals.harness run-suite \
  evals/suites/context-long-task-experiment.yaml --agent lucas-single --trials 1 --runs-root runs
LUCAS_CONTEXT_WINDOW=20000 LUCAS_COMPRESSION_LEVEL=1 .venv/bin/python -m evals.harness run-suite \
  evals/suites/context-long-task-experiment.yaml --agent lucas-single --trials 1 --runs-root runs

# 重读与压缩次数
.venv/bin/python scripts/count_context_rereads.py 'runs/<suite-run>/runs/*'
```

- 任务：`evals/tasks/CTX-01/`（fixture 由 `generate_fixture.py` 确定性生成）
- 套件：`evals/suites/context-long-task-experiment.yaml`
- 测试：`tests/test_ctx_long_task_fixture.py`（ground truth 漂移与答案泄漏保护）
- run 目录（`runs/` 未入版本库）：
  - baseline `context-long-task-experiment-v1-20260807-211220-95fb414c`
  - level2 `context-long-task-experiment-v1-20260807-211854-71ca9ef6`
  - level1 `context-long-task-experiment-v1-20260807-212405-62b78dbb`

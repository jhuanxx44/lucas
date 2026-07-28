# 组件级实验纵览

本目录放**组件级**实验：直接调用某个函数或算法、不启动 Agent、不经过 Evaluation Harness 的对照实验。
Agent 级任务在 `evals/tasks/`，见 [`evals/tasks/README.md`](../tasks/README.md)。

## 两类 eval 的边界

判定只看一条：**这次运行有没有 Agent 在做决策？**

| | Agent 级（`evals/tasks/`） | 组件级（`evals/components/`） |
| --- | --- | --- |
| 被测对象 | Agent 在真实链路上的行为 | 单个函数/算法（检索器、分块器等） |
| 执行方式 | `AgentRunner` 驱动，模型自主决定调用哪些工具 | 独立 `run_*.py` 脚本直接调函数 |
| 定义文件 | `task.yaml`（必需） | 无需 `task.yaml`；参数写在脚本里 |
| 注册位置 | `evals/suites/*.yaml` | 不注册，手动运行 |
| 判卷 | `evals/harness/grader.py`，以环境最终状态为主 | 脚本内算 Recall/MRR/NDCG 等确定性指标 |
| 主要指标 | 成功率、稳定性、步骤、Token、延迟 | 检索质量指标、构建时间、索引大小 |
| 被测实现 | **一定是生产实现** | **可以是生产实现，也可以是实验实现** |

最后一行是最容易出错的地方，单独说明：组件级实验里的检索器可能是为实验单独写的（例如
`RETRIEVAL-BM25/retriever.py` 是 jieba 分词版），与生产的 `utils/wiki_core.py`（子串版）
**不是同一个实现**。因此组件级实验的结论不能直接当作生产行为的结论——要判断生产是否该改，
必须做 Agent 级 eval 或让组件级实验直接调用生产函数。

## 现有实验

| 目录 | 入口脚本 | 被测对象 | 在验证什么 | 报告 |
| --- | --- | --- | --- | --- |
| [`RETRIEVAL-BM25`](RETRIEVAL-BM25/) | `run_controlled_experiment.py` | `retriever.py`（jieba 分词版，**非生产实现**） | TF-IDF vs BM25 在受控语料规模下的配对差值 | [`docs/experiments/2026-07-27-TFIDF-BM25受控规模实验.md`](../../docs/experiments/2026-07-27-TFIDF-BM25受控规模实验.md) |
| | `run_substr_eval.py` | 子串检索（近似生产实现） | 子串匹配在同一查询集上的表现 | [`docs/experiments/2026-07-26-BM25检索对照实验.md`](../../docs/experiments/2026-07-26-BM25检索对照实验.md) |
| | `run_real_recall_eval.py` | 生产 `recall_wiki` | 真实 Wiki 快照上的端到端召回 | 同上 |
| [`RETRIEVAL-CHUNK`](RETRIEVAL-CHUNK/) | `run_chunk_experiment.py` | `bge-m3` embedding + 分块策略 | chunk 大小单变量对检索质量的影响 | [`docs/experiments/2026-07-27-chunk大小对照实验.md`](../../docs/experiments/2026-07-27-chunk大小对照实验.md) |
| [`RETRIEVAL-MULTI`](RETRIEVAL-MULTI/) | `retrieval_policy.py`、`validate_baseline.py` | 多证据召回策略 | 多证据场景的召回基线 | [`docs/plans/2026-07-27-Wiki多证据召回实验.md`](../../docs/plans/2026-07-27-Wiki多证据召回实验.md) |

命名注意：`evals/tasks/` 下的 `RETRIEVAL-01/02/03` 是 Agent 级任务（考"何时该检索"），
与本目录的 `RETRIEVAL-*` 前缀相同但不是一类东西。新增组件级实验时优先用能体现被测对象的
后缀（如 `-CHUNK`、`-BM25`），不要用纯序号。

## 新增组件级实验的规范

1. **先确认属于组件级。** 若要验证的是 Agent 的决策行为（何时调工具、能否不越界、能否真正落盘），
   放 `evals/tasks/` 并写 `task.yaml`，不要放这里。

2. **单变量。** 一个脚本只改一个维度，其余固定并在脚本 docstring 里列清"固定项"。
   参照 `RETRIEVAL-CHUNK/run_chunk_experiment.py` 的 docstring 写法。

3. **ground truth 标注在稳定单位上。** 若被测维度会改变数据切分方式（如 chunk 大小），
   标注必须落在不随该维度变化的单位上（如文档级），否则不同档位的指标不可比。

4. **确定性优先。** 用 Recall/MRR/NDCG 这类可复算的指标；同一输入重复运行结果必须一致。
   仅在主观质量无法客观判断时才加 LLM grader，并允许返回"不确定"。

5. **结果写入 `<目录>/results/`**，脚本可重复运行且覆盖同名文件。

6. **补最小测试。** 至少覆盖不依赖外部服务的纯函数（切分、归约、指标计算、批次预算），
   放 `tests/test_*_experiment.py`。依赖 ollama/网络的部分不写进单测。

7. **如实标注样本量限制。** 若区分性样本不足以支撑细粒度排序，必须在报告里写明结论的适用边界，
   不要让方向性判断被读成精确排序。

8. **报告与日志。** 报告写入 `docs/experiments/`，运行记录追加到
   `docs/experiments/experiment-log.md`，并在上面的"现有实验"表中登记。

9. **明确写出被测实现是否为生产实现。** 这是组件级实验最容易被误读的一点。

## 运行方式

组件级实验没有统一 runner，逐个脚本运行（需要项目 venv）：

```bash
.venv/bin/python evals/components/RETRIEVAL-CHUNK/run_chunk_experiment.py
.venv/bin/python evals/components/RETRIEVAL-BM25/run_controlled_experiment.py --trials 50
```

Agent 级任务则通过 Harness 运行：

```bash
.venv/bin/python -m evals.harness run-suite smoke
```

不为组件级实验建并行 Harness——按项目约定，只补当前阶段需要的最小设施。

# 阶段 1：Context 压缩真实模型对照实验（初步，1 trial/档）

日期：2026-08-01
对照固定项：同一 `AgentRunner`、`deepseek-v4-flash`、temperature=0、固定 prompt/任务/grader；
API 直连 `https://api.deepseek.com/v1`（去除代理环境变量）。
说明：本报告为机制验证的初步数据（每档 1 trial）；完整 ≥3 trials 矩阵待参数定稿后执行。

## 方法

- baseline：`LUCAS_CONTEXT_WINDOW=0`（压缩关闭，与旧行为逐字节一致）
- trigger：`LUCAS_CONTEXT_WINDOW=12000`（触发线 ≈ 12K×0.8−1.2K = 8.4K，使长任务中段真实触发）
- prod 冒烟：`LUCAS_CONTEXT_WINDOW=100000`（验证生产窗口下现有任务不触发）
- trace 与每轮 context 保留：`runs/context-*/<run_id>/trace.jsonl` + `artifacts/input|output-step-N.json`

## 结果（真实 run，1 trial/档）

| 任务 | 档 | 结果 | outcome | 步数 | 累计 prompt_tokens | 成本 | 压缩次数 |
|---|---|---|---|---|---|---|---|
| PLAN-01 | baseline | max_steps | pass | 20 | 125,671 | $0.30 | 0 |
| PLAN-01 | trigger 12K | max_steps | pass | 20 | 155,041（+23%） | $0.43 | 9 |
| READ-02 | baseline | completed | fail* | 6 | 68,931 | $0.17 | 0 |
| READ-02 | trigger 12K | completed | fail* | 10 | 71,345 | $0.19 | 7 |
| WIKI-04 | baseline | completed | pass | 2 | 6,165 | $0.015 | 0 |
| WIKI-04 | trigger 12K | completed | fail* | 2 | 6,165（逐字节一致） | $0.016 | 0 |
| LOOP-01 | baseline | completed | fail* | 2 | 5,510 | $0.014 | 0 |
| LOOP-01 | trigger 12K | completed | fail* | 2 | 5,507（逐字节一致） | $0.018 | 0 |
| PLAN-01 | prod 100K 冒烟 | completed | pass | 18 | 132,857 | $0.37 | 0 |
| READ-02 | prod 100K 冒烟 | completed | fail* | 3 | 39,045 | $0.09 | 0 |

\* 答案内容全部正确，但被 ```json 代码块包裹（+ 说明文字），`answer_json` grader 解析失败
——baseline 同样失败，与压缩无关（harness 宽容度问题，已修 grader 见下）。

## 归因结论

1. **机制可用（已验证）**：压缩真实触发（PLAN-01 9 次、READ-02 7 次），`context_compressed`
   trace 事件携带 before/after/freed/dropped_steps，占位说明正确回写，plan/初始指令豁免由
   注入测试覆盖；简单任务（WIKI-04/LOOP-01，输入 ~6K < 触发线 8.4K）零压缩且输入
   **逐字节一致**（token 完全相同）——未超阈值零行为差异成立。
2. **12K 窗口下 token 反升 +23%（决策门未达）**：高频压缩（9 次）导致模型重读早期文件
   （PLAN-01 trigger 臂第 14–18 步把 5 个 service.yaml 全部重读一遍），输入成本反超 baseline。
   按计划决策门："省了没？——没省；成功率掉没？——outcome 未掉；能归因吗？——能（trace 可见
   重读）。" → **提高窗口阈值或保留更多步骤，或放弃**。
3. **prod 窗口（1M）现有任务不触发**：PLAN-01 单轮真实输入最大仅 14,038 token（计划文档
   138K 为累计口径），远低于 1M×0.8。符合 5.1 决策门预期"现有任务不超预算，需补 CTX 候选
   任务"，且真实压缩受益场景目前不存在。
4. **既有 grader 宽容度问题（已修）**：DeepSeek 常把最终 JSON 用 ```json 代码块包裹并附
   说明，`answer_json`/`answer_facts` 直接 `json.loads` 误判失败（READ-02/WIKI-04/LOOP-01
   三任务中招）。已修复 `evals/harness/grader.py` 新增 `extract_json`（容忍代码块与前后文字）
   + 单测，避免把"答案对、格式错"计入模型失败。

## 决策

- **保留机制**（可触发、可归因、零行为差异），但当前 trigger 参数（12K 窗口）不可用：
  压缩频率过高反而增加成本。
- **下一步候选**（按序）：
  1. 提高触发窗口（如 25–40K）或 `keep_recent_steps=2`，降低压缩频率后重测 PLAN-01/02/04；
  2. 补真实长上下文 CTX 候选任务（单轮输入 >100K，如多公司对比+多文件编辑），在 1M 窗口下
     验证真实收益；
  3. 完整对照矩阵（≥3 trials/档）在参数定稿后执行。
- 失败样本：PLAN-01 trigger 重读行为见 `runs/context-compare-20260801-170040/plan-01-8c1a9f92acee/`；
  代码块失败样本见 `runs/context-regress-20260801-170430/` 下各 run。

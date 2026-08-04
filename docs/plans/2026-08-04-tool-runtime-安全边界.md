# Tool Runtime 超时/取消与命令工具安全边界

日期：2026-08-04
状态：规划（讨论稿，未开始实施）
对应路线图：Phase 1「Tool Runtime 与安全边界」
来源：从 `docs/plans/2026-08-02-lucas-cli.md` 3.4/3.5 拆出。那两节原本挂在 CLI 主线上，
  但其验收全是确定性 grader（路径穿越被拒、超时无残留进程、输出截断），走 eval-driven
  流程，与 CLI 的产品功能验收方式不同，故独立立项。

## 1. 为什么独立于 CLI

命令工具与沙箱不需要 CLI 才能验证：把工具注册进 `evals/harness/adapters/lucas_single.py`，
L1（白名单）+ L2（作用域守卫）+ L4（沙箱）三层就都能在 eval 里跑起来，Phase 1 的验收清单
逐条都能落成 task。

反过来，L3 交互确认在 eval 里没有意义——无人值守跑批没人按 y/n。这恰好是 CLI 规划 3.5
自己的论点：沙箱的价值在「无人值守运行（无 L3 兜底）」时才显现。因此排序是：

- 命令工具与沙箱提前做，不等 CLI；
- `confirm` 回调留在 CLI 的 M6，与终端交互一起落地（届时工具已存在，只需选 profile）。

产品聊天链路不开放命令工具，web profile 不变。

## 2. 待决策：工具形态

路线图第 2 节非目标写「不追求任意 Shell；只支持受限、可审计的测试和诊断命令」，Phase 1
最小工具集给的是两个窄口工具：

| Tool | 能力 | 默认权限 |
|---|---|---|
| `run_tests` | 运行预定义 pytest/npm test target | allowlist、无 shell 插值 |
| `shell_info` | `pwd`、`git status --short` 等诊断 | 严格 allowlist |

CLI 规划 3.4 写的是通用 `run_command`（shell 执行）。两者不是同一个东西，须选其一：

- **窄口版（roadmap 原案）**：allowlist、argv、env 白名单、输出截断、超时杀进程、沙箱
  profile 生成全都练到，且每条都有可写的确定性测试。
- **通用版**：多出来的部分主要是「参数空间无边界」，练的是防注入；grader 更难写。

倾向窄口版，除非学习目标本身就是「面对任意 shell 怎么设边界」。**无论选哪个，两份文档
只留一套说法。**

## 3. 两个硬前提（现在就缺）

这两条不解决，命令工具做出来会破坏已有语义。

### 3.1 `ToolRuntime.execute` 没有超时

`harness/tools/registry.py` 里 handler 是裸 await，没有 `asyncio.wait_for`。现有工具都是
快速本地操作，所以从未暴露；命令工具是第一个可能挂住的工具。

### 3.2 同步 handler 阻塞事件循环且杀不掉

`registry.py` 的 `result = spec.handler(...)` 同步返回就直接阻塞。若命令工具用
`subprocess.run`：

- 整个 SSE 流冻结，`context_usage`、`tool_step` 全部堵在后面；
- `server/services/agent_stream.py` finally 里的 `run_task.cancel()` 收不到效果——前端断连
  与 CLI Ctrl-C 都杀不掉子进程，直接违反 Phase 1 验收的「不残留后台进程」。

因此命令工具**必须**走 `asyncio.create_subprocess_exec`，取消时 kill 整个进程组。
`harness/tools/base.py` 的 `ToolHandler` 类型已允许 async handler，`execute` 也已
`inspect.isawaitable` 兼容，路是通的，只需补超时与取消传播。

### 3.3 顺带的正收益：ToolSpec 扩展有了真实驱动力

`ToolSpec` 现在只有 name/description/parameters/handler 四个字段。Phase 1 设计的
`permissions` / `default_timeout_ms` / `max_output_chars` 之前没扩是对的（没有工具需要）。
命令工具是第一个真正需要 `permissions: process` 与超时上限的工具，此时扩出来的设计不是
凭空想的。

## 4. 沙箱：作为执行后端，可替换

架构落点：**沙箱是命令工具 handler 的执行后端，不是 harness 的概念。** handler 内部从
「直接 subprocess」换成「sandbox-exec 包 subprocess」，ToolRuntime 与 runner 完全无感。

技术阶梯（从轻到重）：

| 方案 | 成本 | 隔离强度 |
|---|---|---|
| `sandbox-exec`（macOS seatbelt）/ bubblewrap（Linux） | 低，包一层 subprocess | 文件系统/网络可配，够用 |
| Apple Container / Docker | 中，维护镜像 | 强，环境可复现 |
| 完整 VM | 高 | 最强 |

### 4.1 实测结论（macOS 26.5.2，2026-08-04）

deny-default profile：

```scheme
(version 1)
(deny default)
(allow process-exec process-fork)
(allow file-read*)
(allow sysctl-read)
(allow file-write* (subpath "/private/tmp/sbtest"))
```

- 写允许目录内成功；写目录外 `Operation not permitted`；
- 不加 `(allow network-outbound)` 时 curl 退出码 6、`http_code=000`，加上后 200。断网开关
  干净可控；
- `sandbox-exec` 自身不往 stderr 喷噪音，包一层不污染工具输出。

**必踩的坑**：profile 里的路径必须是 resolve 过的真实路径。写 `(subpath "/tmp/sbtest")`
会导致连允许目录内的写入都被拒——`/tmp` 是 `/private/tmp` 的 symlink，profile 匹配内核看到
的真实路径。改为 `/private/tmp/sbtest` 后，经 `/tmp/sbtest` 与 `/private/tmp/sbtest` 两条
路径写入均正常。`utils/path_safety.py` 的 `resolve_within` 已是「resolve 后再比较」的正确
模式，生成 profile 时复用同一语义。此坑落地时补一条 `docs/lessons/`。

两点未实测的提醒：

- 上述 profile 的 `(allow file-read*)` 开得很宽。收紧读权限会碰到 dyld/解释器加载，需额外
  允许系统库路径，不要一开始就往死里收。
- `sandbox-exec` 官方已 deprecated 多年（仍随系统发货、仍被 Chrome 等应用使用）。当学习
  载体没问题，但不要在它的 profile DSL 上堆太多东西；想练更强隔离时下一档是 Apple Container。

### 4.2 与 eval 隔离工作区的两个交互点

- `evals/harness/workspace.py` 的 `TrialWorkspace` 每次 `mkdtemp` 到新目录，因此沙箱
  profile 必须**每 trial 现生成**（不能是静态文件），写入根 = 该临时目录的 resolved 路径。
- 同文件 `snapshot_files` 遇到 symlink 会 `raise`。子进程若建了 symlink，判卷会直接炸而非
  给出结论，需一并处理。

## 5. 落地步骤

```
P1a  ToolRuntime 加 timeout + 取消传播；ToolSpec 加 permissions/timeout/max_output
     验收：现有工具行为不变；超时后子进程被杀，无残留
P1b  命令工具（第 2 节决策后的形态）：argv 不用 shell=True、allowlist、
     env 白名单、输出截断
     验收：Phase 1 验收清单逐条落成 eval task
P1c  沙箱后端（sandbox-exec，profile 按 resolved 真实路径每 trial 生成）
     验收：越界写与断网被拒；同一 handler 换后端 ToolRuntime 无感
```

每步可独立停下。P1a 是纯收益：即使命令工具最终不做，超时与取消传播也是现有 ToolRuntime
的缺口。

## 6. 验收标准（取自 Phase 1，全部确定性 grader）

- 路径穿越、symlink escape、禁止目录写入均被拒绝；`raw/` 禁写继承；
- 超长工具输出被截断并保留 `truncated=true`；
- 超时后子进程被终止，不残留后台进程；
- 子进程使用 argv，不用 `shell=True`；
- 敏感环境变量被清理，只传白名单；默认断网；
- 工具参数错误可被 Agent 观察并在下一步修正；
- trace 记录 denied 操作但不泄露敏感值。

## 7. 开放问题

1. 工具形态：窄口 `run_tests` + `shell_info`，还是通用 `run_command`？（第 2 节）
2. `ToolSpec` 新增字段是全工具统一填写，还是带默认值只由命令工具覆盖？
3. 沙箱是否默认开启（eval 里默认开、开发时可关），还是显式 opt-in？


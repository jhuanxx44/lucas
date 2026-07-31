# Current Research: Open-source review of the Lucas harness roadmap

## Scope
- Review planning, not product code.
- Primary evidence should come from official repositories, tests, and maintainers' documentation.
- Popularity alone is not evidence of architectural fitness for Lucas.

## Initial Hypotheses
- `mini-swe-agent` is likely the best primary reference for a minimal loop and Agent/Environment boundary.
- `Inspect AI` is likely the strongest supporting reference for evaluation object boundaries and transcript/log handling.
- `OpenHands` is useful as a mature runtime and sandbox comparison, but is likely too broad to copy.
- Lucas should complete a traceable baseline before introducing Planner, Validator, Context compression, MCP, or general multi-agent orchestration.

## Existing-worktree Note
- `docs/agent-harness-eval-mvp.md` already contains substantial user edits for a single-agent baseline and Lucas-specific smoke tasks. Treat them as the current design, not disposable draft content.

## Phase 1 Audit Findings
- The roadmap already has the right macro-boundary: Agent Harness executes; Evaluation Harness prepares, observes, and grades.
- The roadmap's shortest-path list is internally inconsistent with its phases: it places `RunState`/trace after ToolSpec, while Phase 0 and the Eval MVP correctly require trace from the first baseline.
- Reliability is scheduled as Phase 3, after Planner/Validator. Minimal run/model/tool timeout, terminal reasons, and cleanup are prerequisites for a trustworthy baseline and should be split into a Phase 0/1 reliability floor plus later recovery experiments.
- The target architecture presents Planner, ContextManager, and Validator as permanent central components before experiments prove they help. They should be optional policies/variants around one stable loop, not assumed mandatory architecture.
- The roadmap currently mixes two directory vocabularies (`harness/benchmarks` and `eval_harness/evals`) and two schemas (`TaskSpec` examples differ). The Eval MVP is more concrete and should become the source of truth for Phase 0 naming.
- Phase 6 proposes 24 mostly generic coding tasks, while the edited Eval MVP now correctly starts with six Lucas-shaped, frozen-fixture tasks. Capability expansion should be failure-driven and use a small core plus later regression/holdout splits, not a predetermined category quota.
- Phase 7 puts trace after phases that already depend on trace. HTML replay is legitimately later; trace and manifest are not.
- Current implementation has completed only PR 0's execution boundary: default single mode, explicit multi fallback, one general single research service, prompt annotation, and six focused tests passing. No `eval_harness/`, tasks, trace, structured tools, or baseline report exists yet.
- The current single service is a product-path single research call, not yet the iterative tool-using baseline described by the roadmap. The Eval Adapter must eventually call a shared runtime rather than treating the current service as the final baseline loop.

## Evidence Standard for the Review
- Prefer pinned official repository code and tests over README claims.
- Use documentation to understand intended contracts; verify critical behavior in implementation or tests.
- Treat architectural differences as context-dependent, not automatically as Lucas defects.
- Recommend an adoption only when it closes a current Lucas gap or enables a named experiment.

## Reference Selection Criteria
1. The project exposes enough source and tests to inspect actual control flow.
2. It has a clear strength relevant to one Lucas boundary; no project needs to cover everything.
3. Its abstractions can be studied without making it a Lucas runtime dependency.
4. It is maintained enough that the reviewed revision is meaningful, but popularity is secondary.
5. The reference set must include both Agent Harness execution and Evaluation Harness concerns.

## Discovery Notes
- General search results are noisy and popularity-biased; exact official repositories will be pinned and inspected locally.
- `mini-swe-agent` remains the primary minimal-loop candidate despite generic search ranking newer orchestration projects higher.
- Inspect's surrounding ecosystem consistently describes its primitives as tasks, solvers/agents, scorers, logs/transcripts, and sandboxes; source inspection will verify the separation.
- Newer projects such as Open SWE are useful ecosystem signals but are built on graph/deep-agent abstractions and are a weaker primary fit for Lucas's goal of learning the harness mechanics directly.
- OpenHands remains a useful mature-system reference for sandboxing and evented runtime boundaries, but its current repository/product scope is far broader than Lucas and public discussion also exposes an important distinction: sandbox containment does not itself provide action-level authorization.
- PydanticAI is a candidate supporting reference for typed tool contracts, model-visible retry feedback, usage limits, and eval APIs. It should be inspected selectively rather than adopted as the Lucas loop.

## Selected Reference Set
| Role | Project | Review focus | Explicit non-goal |
|---|---|---|---|
| Primary | `SWE-agent/mini-swe-agent` | smallest real loop; Agent/Model/Environment boundary; history and termination | copy its coding-specific shell interface or prompts |
| Eval | `UKGovernmentBEIS/inspect_ai` | Task/Solver/Scorer/Sample state/log/sandbox/limits boundaries | add Inspect as an MVP dependency |
| Typed contracts | `pydantic/pydantic-ai` | tool schema, retry semantics, usage/step limits, eval separation | replace Lucas with a framework |
| Mature-system check | `OpenHands/OpenHands` | sandbox versus authorization; event/action/runtime separation | reproduce its server/event-bus architecture |

### Reference-set Update from User-provided Local Codex Clone
- Add `openai/codex` at local pinned commit `3151954` as the primary production-boundary reference.
- Downgrade OpenHands to a narrow corroborating source for sandbox-versus-authorization; no further broad source inspection is needed.
- Codex is not a whole-system template: the repository's own `AGENTS.md` warns that `codex-core` became bloated and explicitly resists adding more concepts there.

## Pinned Revisions (reviewed 2026-07-17)
- Inspect AI: `8117bf2ff6acc41de137026e2355dec1c0212dfc`
- mini-swe-agent: `388da74aad620a384ab47669b17c52133e30e7c3`
- OpenHands: `f012a4017c27cefbc8c1f22fa0ac87aac2028d1a`
- PydanticAI: `8481c72789374a5af071be2864b1c8b566a0ff5b`
- Codex: `315195492c80fdade38e917c18f9584efd599304`

## Repository-shape Observation
- mini-swe-agent has distinct `agents`, `models`, `environments`, and benchmark runners, with focused tests around finish reasons, saved trajectories, environments, and model formatting. This is small enough for control-flow study.
- Inspect AI is intentionally much broader: event types, sample state, task resolution, solvers/agents, scorers, sandbox APIs, limits, and eval logs are separate packages. Lucas should borrow boundaries, not its surface area.
- PydanticAI combines a graph-based agent runtime with a separately packaged `pydantic_evals`; selective inspection is necessary to avoid importing framework architecture by accident.
- The current OpenHands repository is a large product/platform monorepo. Its strongest value for this review is checking mature sandbox/event persistence concerns and documenting what Lucas should defer.

## mini-swe-agent Findings
- The real loop is deliberately small: initialize two messages, repeat `query -> execute actions -> append observations`, and stop when the last message has an exit role. Explicit planning, validation, a workflow graph, and a large `RunState` object are not prerequisites for a useful baseline.
- Its stable seams are three protocols: `Agent.run/save`, `Model.query/format observation/serialize`, and `Environment.execute/serialize`. Model-specific message formatting stays in the Model adapter; execution stays in Environment. Lucas's current `AgentAdapter` alone is not enough to define the internal baseline runtime boundary.
- Minimal reliability is part of the loop, not a later feature: step, cost, and wall-time limits are checked before model calls; environment commands have timeouts; timeout kills the process group; trajectories are saved in a `finally` block after every iteration.
- Failures become model-visible messages when recovery is possible. Consecutive format failures have a separate cap, preventing an infinite self-correction loop. Tests distinguish truncation from malformed tool calls using provider finish reasons.
- The serialized trajectory includes messages, model stats, concrete Agent/Model/Environment types, config, version, exit status, and submission. This supports the Lucas requirement that trace/manifest begin with the baseline.
- The design also shows what Lucas should not copy: local execution uses `shell=True`, completion is encoded as a magic shell-output sentinel, actions/results are untyped dictionaries, and environment containment/authorization is outside the minimal loop.

## mini-swe-agent Implications for Lucas
- Keep the baseline as one iterative loop without Planner or independent Validator.
- Define `ModelAdapter` and `Environment` alongside `AgentRunner`; do not let the Eval Adapter become the runtime abstraction.
- Introduce only a small `RunState` (messages, counters, limits, timestamps, terminal result), not the roadmap's eventual Plan/Context/Validation object graph in Phase 0.
- Move step/run/model/tool timeout, terminal-reason normalization, best-effort final trace, and child-process cleanup into the baseline reliability floor.
- Treat provider parse/format errors as a distinct, bounded recovery class; do not count them as normal task steps or blindly map them to generic tool errors.

## Inspect AI Findings — Task and Log Boundaries
- An Inspect `Task` owns a dataset, setup/solver/cleanup lifecycle, scorer/metrics, model config, sandbox, approvals, version/tags, and sample-wide limits. A dataset `Sample` owns input, target, metadata, files, setup, and optional sandbox/checkpoint configuration.
- Limits are not an afterthought: message, token, turn, wall time, working time, and cost limits are task-level configuration and are persisted into per-sample results.
- `EvalSample` separates execution facts (`messages`, `output`, `store`, `events`, usage, timing, error/limit) from scores. This supports Lucas's separation of Agent result, trace, grader result, and efficiency metrics.
- Logs have an explicit schema version. Event payloads can be separated into attachments to keep large content out of the main event sequence. Lucas's JSONL MVP should likewise version its trace schema and reference large artifacts by hash/path rather than embedding everything.
- Scoring occurs after sample execution and can add its own events. This reinforces that an Agent's self-validation must not be the benchmark verdict.
- Inspect is much more feature-rich than Lucas needs. Checkpoint callbacks, resume, approvals, adaptive concurrency, multiple timelines, and log mutation are evidence of eventual concerns, not Phase 0 requirements.

## Inspect AI Findings — Execution, Scoring, and Sandbox
- A `Solver` transforms `TaskState`; the injected `Generate` function owns model generation and supports loop/single/no-tool-call modes. This is an example of keeping an experimental elicitation policy replaceable while retaining shared state and generation plumbing.
- A `Scorer` receives final task state plus the target and returns a score. Lucas should keep reference answers entirely in the Eval Harness/grader path; unlike a general Inspect solver environment, the Lucas Agent Adapter must never receive hidden expected values.
- Inspect's sample state includes model/messages/tools/output/store and limit state, while the log separately records events and final scores. The useful Lucas equivalent is a minimal runtime state plus immutable trace, not one dataclass that mixes task spec, execution, and grades.
- Sandbox execution uses argv, per-sample working directories, timeouts, output limits, and explicit exception types. These belong in Lucas's early environment/tool boundary.
- Inspect can retry timed-out sandbox commands by default. Lucas should retain its stricter planned rule: only retry when operation idempotency and outcome certainty make it safe.
- Approval rejection is still emitted as a structured tool event with an approval error. This validates Lucas's plan that denied actions must be observable facts, not silent filtering or prompt-only rules.
- Cleanup is designed to run in `finally` paths and sample limits are recorded in results/events. Lucas's Eval runner should similarly guarantee workspace/process cleanup and terminal trace emission even when the Agent crashes.

## PydanticAI Findings
- `UsageLimits` separates model request count, successful tool-call count, and input/output/total token ceilings. Request limits are checked before calls; token limits may only be known after a provider response. Lucas should document which budgets are hard preconditions versus best-effort post-response limits.
- `ModelRetry` is not the same as retrying an HTTP request or re-executing a tool. It sends structured feedback to the model and consumes another model turn. Per-tool retry counters and a last-attempt signal bound this correction loop.
- Tool timeout is converted into model-visible retry feedback and counts against a tool retry budget. Tests show the tool may be invoked again. Lucas should not copy this behavior generically because an interrupted write can have an unknown outcome; timeout recovery must respect idempotency/outcome certainty.
- Tool definitions support per-tool timeouts, argument schemas, dynamic preparation, and approval/deferred execution. Only schema, timeout, and permission metadata are needed early; dynamic tool mutation and deferred tools should wait for demonstrated use cases.
- Pydantic Evals explicitly separates static Definition (`Dataset`/`Case`/evaluators), Experiment execution, and `EvaluationReport`. It supports repeating cases, per-case plus suite-wide evaluators, evaluator failures as data, and evaluator version tags.
- Dataset models reject unknown fields. A strict, versioned Lucas `TaskSpec` is preferable to permissive YAML parsing because silent typos invalidate experiments.

## Retry Taxonomy Required for Lucas
The roadmap currently uses “retry” too broadly. The implementation plan should distinguish:
1. **Provider retry**: same logical model call after explicit transient transport/provider failure.
2. **Tool execution retry**: re-run an idempotent operation only when prior outcome is known not to have succeeded.
3. **Model correction**: return invalid input/format/tool feedback to the model and consume another model turn.
4. **Revision**: change the plan/step/answer after validation failure.

Each needs separate counters, budgets, trace events, and experiment metrics. A provider retry should not count as a reasoning step; a model correction should.

## Codex Findings — Production Loop and Tool Boundary
- Despite production complexity, the documented turn skeleton is still the same minimal loop: model returns tool calls or an assistant message; tool outputs feed the next sampling request; an assistant-only response can finish the turn. This strengthens the decision not to make Planner/Validator mandatory core states.
- Codex captures a per-step context once so model-visible context, advertised tool specs, and subsequent tool calls share the same request view. Lucas should snapshot an immutable `StepContext`/request view before each model call rather than reading mutable config/tool state at different times.
- A turn-scoped model client session is reused across retries, while cancellation tokens are threaded through model and tool work. Lucas's ModelAdapter contract should include cancellation/deadline context and should define whether retry reuses provider session state.
- Tool routing separates model-visible specs from the executable registry. `ToolInvocation` carries session, turn, step context, cancellation, diff tracker, call id, tool name, source, and payload. Lucas needs only a smaller equivalent, but tool policy and tracing should receive execution context rather than rely on globals.
- Tool outputs have different projections for model context, telemetry preview, and code-mode consumers. Output truncation is applied to the model-visible projection. Lucas should separate raw artifact, bounded model observation, and redacted trace preview instead of forcing one `ToolResult.content` to serve all consumers.
- Protocol messages use typed discriminated unions and explicit call IDs. This validates stable `ToolCall`/`ToolResult` IDs and typed message kinds in the baseline trace.
- Codex context rules require incremental history, cache-aware stability, and hard caps on every injected item. Lucas does not need compaction in Phase 0, but every observation and injected context item needs a bound from day one.

## Codex Findings — Reliability and Output Projections
- Responses retry code handles retryable stream/transport failures with a bounded counter and backoff, then can fall back from WebSocket to HTTPS while keeping the turn-scoped client session. It does not conflate this with asking the model to repair tool arguments.
- Retry state is user-visible after a noise threshold. Lucas does not need UI behavior in the Eval MVP, but trace must record every retry even if product UI suppresses transient noise.
- Each tool runtime can declare whether cancellation should wait for its teardown. This is a production-grade refinement of the baseline requirement that timeout/cancellation must not leave child processes or unknown cleanup state.
- Tool exposure (what the model may see), routing (what is registered), policy/hooks, execution, telemetry, and model-visible output are distinct layers. Lucas should implement only exposure + policy + execution + trace in Phase 1, but keep their contracts separate enough that approval/MCP do not require rewriting the loop.
- Codex's mature output design reinforces a three-view result:
  1. raw structured result/artifact for deterministic consumers;
  2. bounded observation returned to the model;
  3. redacted bounded preview plus metadata in trace.
- Hooks, dynamic tool search, streamed argument diffs, parallel tool execution, and code-mode nesting are explicitly out of scope until Lucas has evidence for them.

## Codex Findings — Trace, Persistence, and Tests
- Codex separates resumable conversation rollout persistence from a derived/raw rollout-trace subsystem. Lucas should not imply that JSONL trace is automatically a checkpoint; trace, run result, and future resume state are different contracts.
- The trace writer is append-only, assigns a schema version, flushes after events, and writes referenced payload files in an order that avoids events pointing at missing payloads after interruption. Lucas Phase 0 should add `trace_schema_version` and define artifact-before-reference durability.
- Codex integration tests drive the real turn loop with deterministic mocked model streams, inspect subsequent model request bodies, and verify call IDs/tool outputs. Lucas needs one deterministic loop integration test before live-LLM trials, not only `AgentAdapter` and grader unit tests.
- Error integration tests verify both terminal events and release of session/task state so a later turn can run. Lucas baseline tests should verify cleanup/reusability after model error, timeout, and cancellation.
- Codex exposes planning as an ordinary tool/event (`update_plan`) rather than making planning a prerequisite for the underlying turn loop. This is strong production evidence that Lucas should model Planner as an experimental policy/variant.
- Codex's breadth and its own core-bloat warning reinforce a structural guardrail: Lucas's `Manager` remains a product adapter; the minimal loop, environment/tools, trace, and eval runner must not accumulate inside it.

## Comparative Decision Matrix

### Keep
- Eval-first, outcome-first, isolated fixtures, deterministic graders, reference solutions, repeated trials, and single-agent baseline.
- A framework-free Python implementation for the first loop; external projects are references, not runtime dependencies.
- `Manager` as a product consumer/adapter rather than the Harness core.
- Trace from the first executable baseline and HTML replay only after the event schema proves useful.
- Planner, Validator, Context compression, MCP, and multi-agent as separately measurable variants.

### Adjust Now
- Replace the assumed `Planner -> Executor -> Validator` target core with one stable `AgentRunner` loop plus optional policies/variants.
- Define four early seams: `AgentRunner`, `ModelAdapter`, `Environment/ToolRuntime`, and `TraceSink`. Keep `AgentAdapter` outside these as the Eval Harness integration boundary.
- Make Phase 0 state minimal: messages, immutable per-request `StepContext`, counters/usage, deadlines/cancellation, and terminal result. Add Plan/Validation objects only in their experiments.
- Move the reliability floor before baseline trials: max model turns/corrections, run/model/tool timeout, cancellation, terminal reasons, output bounds, process cleanup, and guaranteed final trace.
- Split the current combined Phase 2 into a Planner experiment and a later Validator+Revision experiment so their effects can be attributed.
- Version strict TaskSpec, grader definitions, trace schema, and suites from the beginning; reject unknown YAML keys.
- Separate raw tool artifact, bounded model observation, and redacted trace preview.
- Replace generic retry language with provider retry, tool execution retry, model correction, and revision.
- Make the Eval MVP's `eval_harness/`, `evals/`, TaskSpec, and CLI terminology canonical across the roadmap.
- Grow tasks in layers: atomic smoke -> Lucas business capability -> failure-driven capability additions -> stable regression + held-out capability. Do not commit to category quotas before failures justify them.

### Defer
- Checkpoint/resume, Human-in-the-loop abstraction, dynamic tools, hooks, parallel tool calls, general DAGs, provider fallback, MCP, HTML replay, and distributed/container-scale execution.
- Context compression until baseline traces show a real context-budget failure; first test deterministic selection/removal, then summary compression separately.
- Full cost enforcement when a provider cannot supply trustworthy usage; record best-effort usage and enforce request/turn limits first.

### Remove from the Plan as Commitments
- A predetermined 24-task quota and fixed 288-run final matrix. Keep them as possible scale targets, not architecture milestones.
- The implication that every successful Lucas run must pass an internal LLM Validator. Benchmark graders remain authoritative; internal validation is an optional experiment.
- Any plan to implement the full target object graph before the relevant variant is evaluated.

### Experiments Required
1. `baseline` vs `planner` on tasks stratified by simple/multi-step complexity.
2. `planner` vs `planner+validator+revision`, measuring grader recovery rather than self-reported validation.
3. No-selection vs deterministic context selection; only then selection vs one-time LLM compression.
4. Native tools vs MCP adapter on the same frozen tasks.
5. Single vs multi-agent only after both use the same tools, budgets, task set, and grader.

## Reference Lookup Policy for Future Design Questions
| Lucas question | First reference | Why |
|---|---|---|
| Is the loop still minimal? | mini-swe-agent | exposes the smallest complete Agent/Model/Environment loop |
| What production boundary are we missing? | local Codex clone | cancellation, step snapshots, tool context, output projections, persistence, integration tests |
| Is the evaluation contract trustworthy? | Inspect AI | task/sample/solver/scorer/log/sandbox and limits separation |
| How should schema/retry feedback be typed? | PydanticAI | strict schemas, usage limits, bounded model correction |

Consult references when Lucas has a concrete design question or failure. Do not periodically synchronize Lucas with upstream architectures.

## Final Planning Outcome
- The original direction survives the review; the main optimization is causal ordering, not a framework rewrite.
- Phase 0 now means a trustworthy shared single-agent baseline, including a minimal reliability floor and versioned trace.
- Phase 1 expands the tool contract and safety boundary after the minimal tools needed by baseline exist.
- Phase 2 tests Planner alone; Phase 3 tests Validator/Revision and classified recovery.
- Task count is no longer a milestone. Suites are governed as smoke, capability, regression, and holdout.
- The next implementation slice is Eval PR 1 followed by the shared iterative runtime in PR 2; Planner is explicitly excluded until both smoke and business baselines are frozen.

---

# Review Findings: Responses Migration Release Audit

## Scope Baseline
- Current branch is `feature/dev`; local HEAD and `origin/feature/dev` both start at `4d79259`.
- The worktree contains the completed Responses migration and its documentation/tests. File attribution must be checked before staging because project instructions require preserving unrelated user edits.
- The `codex-collab` skill's required `mcp__codex__codex` tool is not available in this Codex desktop environment; review proceeds with local read-only inspection and deterministic evidence.

## Runner and Streaming Review
- **Fixed P1:** `max_cost_usd` was checked only on the function-call branch. A regression test proved that an over-budget final answer returned `completed`; the post-response budget check now runs before protocol, answer, or tool decisions.
- **Fixed P1:** streamed output deltas were replayed without checking that they equaled normalized final-answer text. A regression test reproduced commentary leakage; non-empty buffered deltas are now reconciled with the completed authoritative answer before publication.
- **Fixed P1:** Responses with `status=incomplete` could be accepted as final answers. The adapter now turns every non-completed response status into a bounded protocol correction instead of accepting partial output.
- Raw reasoning deltas are not rendered as user-visible process steps. They are accumulated into `trace_event/model_reasoning` for trace export, while visible steps continue to use the required function-call `summary`; the earlier hidden-reasoning requirement is preserved.
- The Runner still rejects multiple calls and true final-answer/tool mixtures, preserves provider call IDs, and appends complete response items before `function_call_output`.
- **Fixed trace gap:** transient provider retries occurred inside the client but were not separately observable. The transport now reports sanitized retry metadata through the adapter, and Runner records one `provider_retry` event per retry without counting it as a model correction.
- Unknown tool names currently reach `ToolRuntime` and become model-visible `invalid_input` observations rather than protocol corrections. This remains safe because allowlist enforcement is local, but classification should be checked against existing intended semantics before changing it.

## Tool Schema and Runtime Review
- All production tools expose closed object schemas, and model-only `summary` is injected on a deep copy, so business handlers never receive it.
- Filesystem paths are resolved through `resolve_within` after symlink resolution; write tools cannot escape the workspace, and the product layer further limits writes to `wiki/`.
- The local schema validator covers every constraint currently relied upon for execution safety (types, required fields, closed objects, enum, numeric bounds, nested items). Stock-code `pattern` is additionally enforced by the handler, so the validator's lack of generic pattern support is not a bypass.
- **Fixed P2:** a registered handler returning a non-`ToolResult` value raised outside the handler exception boundary. The runtime now validates the return type inside that boundary and emits a structured `handler_exception`.
- **Fixed configuration edge:** a whitespace-only `DEEPSEEK_MODEL` value previously reached the SDK unchanged; explicit and environment model values are stripped and fall back to `deepseek-v4-flash` when blank.
- No new path-safety or raw-write regression was found in the schema migration.

## Release Validation
- Focused review regressions: 73 passed.
- Full non-live backend suite: 283 passed.
- Frontend production build and changed-file ESLint: passed.
- Live DeepSeek official Responses smoke: passed with `deepseek-v4-flash` and usage returned.
- `git diff --check`, prompt weight audit, forbidden production-reference scan, and `raw/` status: clean.
- Remaining forbidden-reference matches are confined to historical plans/experiments and the migration deletion checklist; they describe past behavior and are not executable/current configuration.

---

# Findings & Decisions

## Requirements
- Remove “原始资料” from the primary frontend navigation.
- Add ChatGPT-like persistent conversation history.
- Treat one session as one continuous topic with multiple turns.
- Support create, switch, rename, delete, and refresh recovery in the first version.
- Preserve Wiki navigation, ingestion capability, and SSE chat behavior.
- Never modify or delete `raw/`.
- Stream Lucas execution progress in the frontend and collapse it after the final answer.
- Do not expose raw hidden chain-of-thought; show factual process milestones instead.

## Research Findings
- `App.tsx` owns the left rail and currently switches between `WikiSidebar` and `RawSidebar`; replacing the raw tab can be isolated there.
- `useChat` owns all messages in a reducer and loses them on reload; `ChatPanel` is currently uncontrolled.
- The chat request already sends the full prior message history, so loading a persisted session into `useChat` preserves multi-turn model context without changing the LLM pipeline.
- `LocalWorkspace.memory_root` is the existing non-raw, single-user persistence boundary. A `memory/sessions/` directory fits the current architecture and keeps `raw/` untouched.
- The simplest reliable persistence boundary is completed UI messages: save the full message list only after `done` or `error`, avoiding partially persisted assistant responses.
- Existing session switching can remount `ChatPanel` with loaded messages by using the active session id as its React key; this avoids a complex reducer reset protocol.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use the existing visual system | The supplied screenshot is evidence of current UI density and styling; the requested change is structural rather than a new visual brand |
| Replace tabs with `对话` and `Wiki`, defaulting to `对话` | Directly substitutes the low-value raw view while keeping Wiki one click away |
| Store one JSON file per session under `memory/sessions/` | Local, debuggable, isolated from raw data, and avoids rewriting a monolithic history file |
| Persist the full completed message list via API | Keeps backend storage simple and makes session reload deterministic |
| Auto-title `新对话` from the first user message | GPT-like behavior without adding another LLM call or `llm-weight` requirement |
| Use focused components and primitive callback dependencies | Follows the React skill's component ownership and rerender guidance without speculative state libraries |
| Persist process steps on assistant messages | Completed sessions retain an auditable trace while live state can remain expanded |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Browser detected a `ChatPanel` Hook-order change after the live code update | Source hook order was stable; a brand-new tab had no errors, confirming stale Vite HMR state rather than a production bug |
| A live QA request was canceled when the development page hot-reloaded | No console/app error; rerun after all frontend edits have stopped |
| `新对话` can appear both as action text and as an untitled session title | Browser actions must use the unique structural action control, not global text matching |
| Row management controls use hover opacity | Human pointer interaction is normal; browser automation needs force click after uniqueness verification for an unhovered row |
| Current desktop panel widths are unusable at 390×844 | Mobile needs full-width chat plus an on-demand navigation drawer; desktop resizing should remain unchanged |
| Existing in-app tab could not attach for process QA | Opened a fresh localhost test tab using the same browser binding |

## Streaming Process Findings
- Current backend events already describe actual execution milestones; no raw model thought tokens are needed.
- Completed messages can persist `processSteps` through the existing session JSON API without backend schema changes.
- Browser loaded an existing user session, so process QA will create a separate temporary conversation rather than mutate prior history.
- Live browser QA shows an expanded `分析过程 / 实时更新` panel immediately after submit.
- The list grew from `已收到问题` to include backend-streamed `正在分析问题...` and `正在思考...` before the answer completed.
- After completion, the live panel becomes a closed `分析过程 · 3 步` disclosure above the final answer.
- A full page reload preserved the closed process disclosure and final answer with zero console errors.

## Resources
- `web/src/App.tsx`
- `web/src/hooks/useChat.ts`
- `server/routers/chat.py`
- `workspace.py`
- `web/src/components/ChatPanel.tsx`
- `web/src/lib/api.ts`

## Visual/Browser Findings
- The current left rail has two top tabs, “Wiki” and “原始资料”.
- The raw-material view uses most of the rail for internal source folders, displacing conversation history.
- The existing Lucas UI uses a narrow rail, low-contrast borders, indigo selection states, compact typography, and open list rows rather than cards.
- First browser run showed the intended `对话` / `Wiki` tabs and `新对话` control, but React stopped rendering ChatPanel due a Hook-order runtime error.
- A fresh tab loaded successfully with no console errors: `对话` is selected, sessions are grouped under `今天`, Wiki remains available, and the chat composer renders normally.
- Stable live QA completed two turns in the same session; both user and assistant messages remain visible and the sidebar auto-title changed from `新对话` to the first user prompt.
- Reload recovery passed: both persisted assistant messages rendered after a full page reload.
- Creating a new conversation immediately adds a selected `新对话` row while retaining the previous titled session; the main panel resets to the empty-state suggestions.
- Switching back to the older session restores both turns without a reload; the row-level management menu exposes only `重命名` and `删除`.
- Inline rename succeeds via Enter and updates the sidebar title to `两轮会话测试` without disturbing the active conversation.
- Delete uses an inline `确认删除？` state instead of a browser modal; confirming removed the empty session while preserving the active two-turn session.
- Wiki remains fully accessible through its tab, and the `原始资料` tab count is zero.
- Desktop screenshot shows a balanced 240px conversation rail, selected indigo session row, open message canvas, and unchanged dark-theme typography/borders.
- Browser viewport override is available; responsive QA will use 390×844 and reset to the default afterward.
- Initial 390×844 screenshot failed responsive QA because the desktop sidebar and chat were compressed side-by-side.
- After the responsive fix, 390×844 shows full-width chat with readable messages and composer; the menu opens a 280px conversation/Wiki drawer over a dimmed canvas.
- Final mobile page reload had no app console errors; a browser-control timeout occurred only while waiting for the drawer overlay to detach.

## Fidelity Ledger
| Comparison point | Reference evidence | Final render evidence | Result |
|------------------|--------------------|-----------------------|--------|
| Navigation hierarchy | Two compact top tabs above a narrow rail | `对话` and `Wiki` remain in the same position; internal raw view removed | Match with requested IA change |
| Brand and typography | Lucas wordmark, muted tagline, compact rail labels | Same wordmark/tagline hierarchy and 11–14px control typography | Match |
| Accent and states | Indigo tab underline and selection color | Indigo underline, selected session row, and user-message surfaces | Match |
| Container model | Open sidebar list with subtle borders, no card grid | Open date-grouped session list with one outlined `新对话` action | Match |
| Icon treatment | Thin outline utility/folder icons | Existing Lucide outline family used for chat, add, menu, rename, and delete | Match |
| Density and spacing | Tight 8–12px chrome spacing | Rail rows, header, composer, and message spacing stay within the same compact rhythm | Match |
| Responsive behavior | Supplied crop emphasizes a narrow navigation surface | 390×844 uses full-width chat and an on-demand 280px drawer | Improved for the new workflow |

## Above-the-fold Copy Diff
- Removed as requested: `原始资料`, `收录材料`, and raw folder labels from the primary UI.
- Added as required: `对话`, `新对话`, date group labels, and persisted session titles.
- Preserved: `Lucas`, `投研认知的复利引擎`, `Wiki`, search, theme, and linked-navigation controls.
- Intentional visual state difference: final evidence uses the user's persisted dark theme; the supplied screenshot used light theme. Component colors remain paired light/dark tokens.
## 2026-07-31 — Native Responses Migration Findings

### Initial authoritative findings
- The current direct DeepSeek path uses `responses.create`, but only for text/JSON transport; AgentRunner still owns a custom `action/tool/args/reply` text protocol.
- Native migration affects more than `utils/llm_client.py`: Runner history/decision parsing, ToolSpec schemas, streaming, SSE, config, knowledge services, scripts, tests, trace, dependencies, and current documentation all contain legacy assumptions.
- `ToolSpec.args_description` is prose, so every production tool needs an explicit JSON Schema before strict native function calling is possible.
- Current provider configuration is only partially authoritative: `providers.yaml` declares providers, while LLM routing also hard-codes model prefixes and environment overrides.
- Existing planning files contain completed historical tasks; the migration plan is prepended and old records are preserved as archive data.

### Decisions
- Target is a single DeepSeek official Responses implementation, with no Chat Completions/Gemini/provider compatibility layer.
- Lucas will submit explicit response/function-call/function-output items rather than depend on `previous_response_id`.
- User-visible step summary will be a required model-facing function argument and stripped before ToolRuntime execution.
- Final answer will be direct output_text; JSON reply extraction and action parsing will be deleted.

### Code-shape findings
- `AgentRunner` currently couples four responsibilities to raw JSON text: prompt rendering, action parsing/correction, assistant/tool textual history, and answer streaming through `AnswerStreamParser`. The native rewrite must change these together rather than patching only the model client.
- Existing deadline, cost, observation truncation, repeated failed-call detection, repeated-result stall detection, tool events, trace artifacts, and max-step termination are valuable provider-neutral logic and should be retained around the new `ModelTurn` decision.
- Eval production adapter (`evals/harness/adapters/lucas_single.py`) constructs the same product `AgentRunner`, so the migration can test production behavior without a parallel harness; its model adapter and config wiring must change.
- Knowledge/corpus scripts call the generic text client directly and need a simple Responses text method independent of Agent function calling.
- `requirements.txt` only needs `openai` after the migration; `google-genai` is used by the legacy client path and is a deletion candidate after repository-wide verification.
- Current `ToolRuntime.describe()` and system-prompt tool injection become obsolete once every `ToolSpec` has a strict JSON Schema; ToolRuntime execution itself remains the authoritative allowlist/handler boundary.

### Real DeepSeek Responses capability probe
- Native function calls work with flat Responses function tool definitions, strict JSON Schema, `tool_choice="auto"`, and `parallel_tool_calls=False`.
- DeepSeek thinking mode rejects `tool_choice="required"` with HTTP 400; the implementation must use `auto` and validate decisions in Runner code.
- Explicit continuation without `previous_response_id` works by submitting `[*response.output, function_call_output]`; the full prior output includes reasoning and function_call items and must be preserved.
- Strict structured text works with `text.format.type=json_schema` and returns parseable output_text.
- Actual streaming types include `response.reasoning_text.delta`, `response.output_text.delta`, `response.function_call_arguments.delta`, and the corresponding done/output-item events.
- The complete tool call is reliably available from `response.output_item.done.item`; it contains provider `call_id`, name, JSON-string arguments, and status.
- Usage exposes input_tokens, output_tokens, total_tokens, cached input detail, and reasoning token detail.

### Baseline evidence
- Deterministic migration-relevant suite: 161 passed in 8.17s; only a Google GenAI dependency deprecation warning appeared.
- LOOP-01 baseline passed in 2 model steps with 1 wiki tool call, 5.880s, 5,337 tokens, and $0.016534 recorded cost.
- PLAN-01 baseline passed in 14 model steps with 12 tool calls, 87.936s, 68,197 tokens, and $0.249934 recorded cost; one empty/invalid model output self-corrected, and optional update_plan usage did not pass.
- Baseline artifacts are under `/tmp/lucas-responses-baseline`; task/grader validation for LOOP-01 and PLAN-01 passed.

### Impact-audit additions
- Keep high-level trace event names used by graders where their semantics remain valid, while adding Responses-specific response/call events; this limits unrelated grader churn without retaining the old protocol.
- Eval task fixtures and graders can remain; fake model contracts and the production lucas-single adapter must migrate to ModelTurn/ModelEvent.
- Frontend SSE can remain stable, but ChatRunConfig and TracePanel trace completeness/export must be updated if provider/tool-description or model input/output fields change.
- Direct structured-output consumers and the agent loop need distinct methods on the same Responses transport; native tools must not be forced into knowledge/corpus calls.
- Strict schemas should use canonical model-facing inputs. Legacy handler tolerance may remain if it is business input tolerance rather than model-protocol compatibility.

### Implementation decisions now encoded
- `ModelTurn.function_calls` is a list so Runner can reject multiple provider calls instead of silently selecting one.
- Invalid/missing call IDs, malformed arguments, missing summary, multi-call, mixed tool+text, and empty decisions are protocol corrections with a separate bound, not ToolRuntime errors.
- Final text deltas are buffered until `response.completed` proves the turn is an answer; this prevents a mixed tool/text response from leaking partial final UI output.
- Provider response items are serialized once and reused both for trace artifacts and the next explicit Responses input before appending function_call_output.
- Responses output token details are split into completion and thinking tokens so existing cost calculation does not double-charge reasoning tokens.
- A real call using the production read_file schema confirmed DeepSeek accepts strict schemas whose optional properties are not listed in required; the adapter does not need nullable placeholders or forced defaults.

### Product SSE/trace findings
- Product SSE already has the desired stable visible events (`summary`, `tool_step`, `synthesis_chunk`, `done`, `error`); only internal model input/output payloads and construction need migration.
- Existing server code buffers native reasoning and emits it as hidden `trace_event/model_reasoning`; this behavior should remain while source events switch to ModelEvent.
- Frontend ChatRunConfig currently requires provider and prose tools_description. The native config should instead expose a fixed protocol and structured tool schemas, and trace export schema must be bumped.
- Trace completeness can retain high-level model_input/model_output/assistant_answer events because they remain meaningful with native items; Responses-specific response/call events supplement rather than replace them.

### Integration findings
- Visible product SSE did not need a breaking event change; summary now comes from native function arguments, while tool_step and synthesis_chunk retain their UI contracts.
- The previous product runtime trace omitted authoritative run lifecycle/assistant-answer events required by its own frontend completeness check; the migration now emits run_started, assistant_answer, and run_finished explicitly.
- Direct knowledge and corpus generation can share the Responses transport through generate_text without acquiring Agent tool-loop semantics.
- Existing eval graders rely on stable tool_call_started/finished/error events, which the native Runner retained; task fixtures and grader implementations therefore remain production-relevant without protocol compatibility code.
- Historical `docs/superpowers` plans still describe the implementation that existed when they were written; per the migration plan they remain immutable factual history rather than current documentation.
- Remaining `provider` terminology in stock_data and daily stock source documentation refers to market/search data providers, not LLM routing, and must not be mechanically deleted.

### Post-migration eval regression findings
- The latest native implementation remains deterministically sound: the schema/planner/business/Runner slice passes 102 tests and the full non-live backend suite passes 271 tests.
- `LOOP-01` asks for a bare JSON object, but the production Runner currently has no task-specific final-output schema. This is a final-answer contract issue, not a native function-call parsing issue.
- The eval adapter still contains `extract_json` post-processing. That convenience must not become the production protocol again; any JSON requirement should be represented explicitly at request/task boundary or enforced by the grader/task prompt, while normal product answers remain direct text.
- `PLAN-01` is a genuine execution regression: rejecting native multi-call and mixed text/tool decisions consumed three of twenty model turns before useful work. The correction path needs targeted prompt/loop treatment without executing parallel calls or reviving the old JSON envelope.
- DeepSeek emits tool-turn prose as a Responses `message` with `phase=commentary`; `response.output_text` aggregates it even though it is not a `final_answer`. The adapter must separate message phases before Runner decision validation.
- The first PLAN response still contained two function calls despite `parallel_tool_calls=False`. Lucas must keep code-side single-call validation and explicitly ask for at most one `function_call` item per response.
- Model correction continues to consume a model turn by design, consistent with Lucas's existing retry taxonomy; it has an independent correction bound and still counts toward model-step budget. The targeted phase fix removes false corrections without redefining max-step semantics during this migration.
- After phase separation, LOOP-01 returned bare `{"in_wiki": false}` and passed all graders in two steps. This confirms the answer-format prompt is sufficient without reintroducing eval-side JSON extraction.
- PLAN-01 after phase separation passed its actual pytest outcome and allowed-diff safety checks, but ended at max steps immediately after a final corrective patch. The remaining waste was one provider multi-call correction, reading tests/archive without task need, and three read-after-write checks; prompt policy should prioritize required outputs and evidence-based completion.
- The PLAN-01 fixture sentence had dependency direction reversed relative to both its listed gates and deterministic test. It was corrected to “被依赖方先部署，依赖它的服务后部署” so the evaluation no longer rewards test-file discovery over following the stated specification.
- On the final implementation, three independent LOOP-01 trials all passed and three independent PLAN-01 trials all passed. Outcome stability is restored, but PLAN-01 averages 19 model turns and 138k tokens versus the migration baseline's 14 turns and 68k tokens.
- Every final PLAN-01 trial still had 1–2 genuine multi-call corrections even with `parallel_tool_calls=False` and explicit prompt wording. This is a measured DeepSeek compatibility boundary, not a remaining Lucas parsing bug.
- Final PLAN-01～04 outcome is 3/4: PLAN-01, PLAN-03, and PLAN-04 pass; PLAN-02 exhausts 24 steps before report/index completion. The latest comparable legacy run also had semantic 3/4 with PLAN-02 as the failure, so migration does not reduce that suite's observed outcome, but it materially increases context tokens on long tasks.
- Explicitly resubmitting full Responses output items makes trace/replay self-contained, but input growth is now the dominant efficiency cost. Context selection/compaction should be a separate eval-driven experiment rather than folded into this protocol migration.

---

# Current Task Plan: Review, Fix, Commit, and Push Responses Migration

## Goal
Systematically review the complete Responses-native migration, fix verified issues without expanding scope, rerun risk-proportionate validation, then commit and push the reviewed migration to the current `feature/dev` branch.

## Current Phase
Phase 5 — stage, commit, push, and verify the reviewed migration

## Phases

### Phase 1: Scope and Baseline
- [x] Attribute every dirty file to the migration or pre-existing user work
- [x] Review branch/upstream state, deleted files, configuration, dependencies, and prompt annotations
- [x] Establish the current deterministic and frontend baseline
- **Status:** complete

### Phase 2: Systematic Review
- [x] Review transport, adapter, Runner, tool schemas/runtime, SSE/frontend, eval, scripts, docs, and tests
- [x] Check security, timeout/retry/cancellation, context fidelity, streaming, trace, and terminal semantics
- [x] Record only evidence-backed findings with severity and reproduction
- **Status:** complete

### Phase 3: Targeted Fixes
- [x] Add or locate a failing test for each verified code issue
- [x] Apply minimal fixes and remove any migration-created dead code
- [x] Re-run focused tests after each fix
- **Status:** complete

### Phase 4: Release Validation
- [x] Run full backend suite, frontend build/lint, live connectivity smoke, forbidden-reference scan, and diff checks
- [x] Confirm `raw/` remains untouched and review final staged diff
- [x] Confirm experiment/learning/planning records match final evidence
- **Status:** complete

### Phase 5: Commit and Push
- [x] Stage only reviewed in-scope files
- [x] Create a Chinese commit message
- [x] Push `feature/dev` to its configured upstream and verify remote state
- **Status:** complete

## Success Criteria
1. Every staged file is attributable to the Responses migration or this review's necessary fixes.
2. No unresolved P0/P1 correctness, safety, protocol, or data-loss finding remains.
3. All required tests and product checks pass from the final tree.
4. `raw/` is unchanged and unrelated user work is not staged.
5. The commit exists locally and `origin/feature/dev` resolves to the same commit after push.

## Constraints and Decisions
- Review is authorized to fix migration issues, commit, and push the current branch.
- Do not install the unavailable Codex MCP globally; use local evidence-backed review as fallback.
- Preserve unrelated user changes and do not rewrite history.
- Keep the migration single-provider and Responses-native; do not restore compatibility layers.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| Codex collaboration MCP is unavailable in this environment | 1 | Record the skill limitation and use local diff review, static analysis, focused tests, and independent evidence instead of installing global tooling |
| Four focused regression tests failed for the reproduced review findings | 1 | Confirmed the failures before implementation; apply the minimal fixes and rerun the same tests |

---

# Archived Task Plan: Migrate Lucas fully to native Responses API

## Goal
Implement `docs/plans/2026-07-31-responses-native-migration.md` end to end: DeepSeek official Responses API only, native function calling and function_call_output, direct output_text answers, explicit Lucas-owned context, no legacy JSON action protocol or multi-provider compatibility.

## Current Phase
Complete

## Phases

### Phase 1: Probe, Baseline, and Audit
- [x] Verify DeepSeek Responses function calling, strict schemas, call_id/output chaining, streaming, reasoning, usage, and failure behavior
- [x] Freeze baseline on the selected agent eval/product scenarios
- [x] Inventory production, test, prompt, config, dependency, trace, and documentation changes
- **Status:** complete

### Phase 2: Native Protocol and Tool Schemas
- [x] Introduce provider-neutral ModelRequest/ModelTurn/FunctionCall/ModelEvent types
- [x] Replace ToolSpec string args descriptions with JSON Schema
- [x] Add required model-facing summary and strict tool-schema conversion
- **Status:** complete

### Phase 3: Responses Client and Runner Loop
- [x] Replace multi-provider LLM client with one DeepSeek Responses client
- [x] Rewrite AgentRunner around native function_call/function_call_output and direct output_text
- [x] Preserve execution safety, budgets, deadlines, retries, correction bounds, trace, and artifacts
- **Status:** complete

### Phase 4: Streaming, Prompt, Config, and Services
- [x] Replace JSON answer streaming with native Responses events
- [x] Simplify agent-loop prompt and remove tool descriptions from prompt rendering
- [x] Remove provider routing/config and update product/knowledge/script call sites
- **Status:** complete

### Phase 5: Legacy Deletion and Test Rewrite
- [x] Delete legacy JSON action parsing, AnswerStreamParser, Chat Completions, Gemini, providers.yaml, and obsolete dependencies/docs
- [x] Rewrite fake models, Runner tests, SSE tests, LLM tests, config tests, and knowledge tests for native types
- [x] Pass focused and full deterministic suites
- **Status:** complete

### Phase 6: Eval, Real Smoke, and Documentation
- [x] Run post-change trials with baseline-equivalent task/model/tool/environment/budget settings
- [x] Compare outcome, stability, steps, latency, token usage, retries/corrections, summary, and trace
- [x] Write experiment report, experiment-log entry, and learning document
- [x] Run real DeepSeek product/knowledge smoke and forbidden-reference audit
- **Status:** complete

## Success Criteria
1. Production agent calls tools only through native Responses function calls and returns final output_text directly.
2. Tool results are sent as function_call_output with validated call_id; Lucas explicitly owns submitted context items.
3. ToolRuntime security, permissions, timeout, budget, repeated-failure, retry/correction, trace, and outcome semantics remain enforced in code.
4. No production/current prompt/config/current documentation references the legacy protocols or providers listed in the migration plan.
5. Focused tests, full tests, frontend build where affected, fixed eval trials, and real DeepSeek smoke pass with recorded evidence.
6. Required experiment and learning documents are present and honest about capability/eval results.

## Constraints and Decisions
- `raw/` is immutable and must remain untouched.
- Preserve unrelated dirty-worktree changes.
- No long-lived compatibility layer; temporary intermediate states are allowed only during implementation.
- Responses server-side conversation state is not a correctness dependency; do not use previous_response_id in this migration.
- Execution semantics and reliability remain code-enforced; prompts only guide model behavior.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| None yet | 0 | — |
| Planning status patch used stale section ordering and failed context verification | 1 | Read the current plan header and applied a smaller exact patch |
| Frontend build found App passed onLiveTraceChange but ChatPanel lacked the prop | 1 | Added the missing typed prop and synchronized live native runtime trace state |
| Canonical update_plan patch used stale schema wording and failed context verification | 1 | Read the exact file and replaced the legacy-tolerant tool definition atomically |
| Agent wait was called with an unsupported 1-second timeout | 1 | Use the documented minimum 10-second timeout for subsequent waits |
| Trace artifact query assumed each output artifact was an object, but it is a raw response-item array | 1 | Read the artifact shape directly and query response metadata from trace events instead |
| Frontend Vite build became idle for nearly two minutes after TypeScript completed | 1 | Stop the hung process, inspect the idle Vite process, and rerun the build separately with CI mode before treating it as a regression |

---

# Archived Task Plan: Review Lucas against open-source agent harnesses

## Goal
Deeply review Lucas's learning-by-building roadmap against selected open-source agent harness and evaluation projects, then make evidence-backed, minimal updates to the roadmap and Eval MVP without changing product code or `raw/`.

## Current Phase
Complete

## Phases

### Phase 1: Scope & Baseline Audit
- [x] Inventory current roadmap, Eval MVP, implementation progress, and unresolved design assumptions
- [x] Define comparison questions and evidence standards
- **Status:** complete

### Phase 2: Open-source Research
- [x] Select primary and supporting references using explicit criteria
- [x] Pin reviewed revisions and inspect official code, tests, and documentation
- [x] Record findings after every two research operations
- **Status:** complete

### Phase 3: Comparative Review
- [x] Compare loop, state, tools, context, termination, reliability, trace, eval, and sandbox boundaries
- [x] Classify decisions as keep, adjust, defer, remove, or experiment
- **Status:** complete

### Phase 4: Planning Updates
- [x] Write a concise source-backed design review
- [x] Update the learning roadmap and Eval MVP only where conclusions require it
- [x] Preserve existing user edits and avoid implementation changes
- **Status:** complete

### Phase 5: Verification
- [x] Check cross-document terminology, phase order, links, and contradictions
- [x] Review diff scope and confirm `raw/` is untouched
- **Status:** complete

### Phase 6: Delivery
- [x] Summarize material changes, unresolved experiments, and the next execution slice
- **Status:** complete

## Success Criteria
1. Every material roadmap change is supported by source evidence, a Lucas failure mode, or an explicit experiment need.
2. The review distinguishes Agent Harness from Evaluation Harness and avoids copying an entire framework.
3. The optimized plan says what not to build yet, not only what to add.
4. Phase 0 has a concrete, minimal route to a credible single-agent baseline.
5. Existing product code, user edits, and `raw/` remain untouched.

## Review Questions
1. Is Lucas's proposed single-agent baseline minimal and behaviorally well-defined?
2. What is the smallest useful Agent/Environment/Model/Tool contract?
3. Which termination, budget, error, and retry semantics must exist before planning?
4. What trace is needed from the first baseline rather than retrofitted later?
5. Is the Eval MVP's Task/Trial/Grader/Workspace split sufficient and trustworthy?
6. Which roadmap phases are ordered by learning dependency, and which are merely feature inventory?

## Constraints
- Do not modify or delete `raw/`.
- Do not change product code in this task.
- Preserve the existing modified `docs/agent-harness-eval-mvp.md` content and all unrelated worktree changes.
- Use prompts for model behavior; use code for execution semantics and reliability.

## Errors Encountered
| Error | Attempt | Resolution |
|---|---:|---|
| Adding the review document failed because Markdown backticks terminated a JavaScript template literal | 1 | Switch to a line-array patch builder that does not interpolate Markdown |
| Large roadmap replacement produced an invalid `NaN` patch line in the JavaScript wrapper | 1 | Split the roadmap update into small independently verified patches |
| Combined Phase 9/directory patch did not match the current roadmap context | 1 | Read the exact section and apply two focused patches |
| A verification `rg` pattern with Markdown backticks triggered shell command substitution | 1 | Record the harmless failure and use single-quoted patterns for subsequent scans |

---

# Task Plan: Replace raw-material navigation with persistent chat sessions

## Goal
Make Lucas conversation-first: remove raw-material browsing from the primary UI and add persistent multi-turn chat sessions with create, switch, rename, delete, and refresh recovery.

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] Capture product intent and constraints
- [x] Inspect current frontend state flow, API structure, and local workspace persistence
- [x] Record findings and confirm the smallest viable architecture
- **Status:** complete

### Phase 2: API & Persistence Design
- [x] Define session/message schema and filesystem location outside `raw/`
- [x] Define list/create/read/rename/delete/update behavior
- [x] Add API contract tests before implementation
- **Status:** complete

### Phase 3: Backend Implementation
- [x] Implement session storage and routes
- [x] Persist completed user/assistant exchanges without breaking SSE
- [x] Run focused backend tests
- **Status:** complete

### Phase 4: Frontend Implementation
- [x] Replace raw-material tab with session history sidebar
- [x] Wire new/switch/rename/delete and refresh recovery
- [x] Preserve existing Wiki navigation and chat behavior
- **Status:** complete

### Phase 5: Testing & Verification
- [x] Run backend tests, frontend lint/build, and diff checks
- [x] Browser-test new session, multi-turn persistence, switching, rename, delete, and reload
- [x] Compare the rendered UI against the existing Lucas visual system
- **Status:** complete

### Phase 6: Delivery
- [x] Review changed files and unrelated worktree changes
- [x] Complete plan/progress records and hand off results
- **Status:** complete

### Phase 7: Streaming Analysis Process
- [x] Audit current SSE status and researcher events
- [x] Add persistent process-step state to chat messages
- [x] Render live expanded process and completed collapsed process
- [x] Add focused tests/build checks and browser verification
- **Status:** complete

### Phase 8: Updated Delivery
- [x] Review changes and confirm raw thinking remains hidden
- [x] Complete records and hand off
- **Status:** complete

## Success Criteria
1. The primary sidebar no longer exposes `raw/` or an “原始资料” tab.
2. A new conversation creates one persistent session containing multiple turns.
3. Sessions survive browser refresh and can be switched, renamed, and deleted.
4. Existing Wiki browsing and live SSE chat still work.
5. No implementation or test writes to, edits, or deletes anything under `raw/`.

## Key Questions
1. Where should local single-user sessions live so they are isolated from research memory and raw materials?
2. Should messages be saved at submit time or only after an SSE response completes?
3. How can the existing `useChat` reducer load a session without duplicating state?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| One session contains multiple turns | Matches ChatGPT-like continuity and the user's clarified intent |
| Preserve existing Lucas visual language | This is an information-architecture feature, not a broad visual redesign; no Image Gen concept is needed |
| Keep raw ingestion backend capabilities | The request removes raw browsing from the frontend, not ingestion or compilation behavior |
| Persist per-session JSON under `memory/sessions/` | Uses the existing workspace persistence boundary and keeps `raw/` untouched |
| Save completed message arrays, not partial SSE state | Simple recovery semantics and no partially rendered assistant records |
| Show execution trace rather than raw chain-of-thought | Meets the requested streaming/folding UX with factual, auditable process events |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Session API tests fail because `server.routers.sessions` does not exist | 1 | Expected red test; implement the router and store next |
| Frontend lint reports `useChat` ref access plus pre-existing `WikiContent` effect state update | 1 | Move this task's ref update into an effect; leave unrelated Wiki code unchanged |
| Browser reports changed Hook order in `ChatPanel` and renders loading fallback | 1 | Inspect `useChat` hook layout and distinguish source bug from stale HMR state before retrying |
| First live turn was reset before completion by a development hot reload | 1 | Stop frontend edits during QA and rerun the flow on the now-stable page |
| Browser locator for `新对话` expected two exact-name buttons but count differed | 1 | Inspect the fresh DOM and use a structurally scoped locator instead of retrying ambiguity |
| Rename menu locator timed out after its UI state became stale | 1 | Re-snapshot, reopen the row menu, then act on the fresh menu state |
| Empty-session management click timed out because the hover-only button is visually hidden | 1 | Confirm uniqueness from fresh DOM and use a force click for automation only |
| 390×844 viewport compresses the fixed desktop sidebar and chat into an unusable strip | 1 | Add a mobile navigation drawer and make chat full-width below `md` |
| Browser tooling logged an unrelated Statsig network failure while capturing the mobile drawer | 1 | Treat as Codex browser telemetry noise; app DOM and screenshot completed successfully |
| Planning-record patch context did not match | 1 | Read current record tails and apply a precise patch |
| Final mobile drawer-close wait timed out and reset the browser control kernel | 1 | Reconnect and perform a read-only final-state check instead of repeating the wait |
| Existing browser tab could not attach during process QA | 1 | Follow troubleshooting guidance and use a fresh tab in the same browser |

## Notes
- Existing unrelated worktree changes must be preserved.
- `raw/` is strictly read-only.
- New LLM calls are out of scope; no new `llm-weight` annotation should be needed.

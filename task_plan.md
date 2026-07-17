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

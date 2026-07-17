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

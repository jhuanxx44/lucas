import { useReducer, useCallback, useEffect, useRef } from "react";
import { useSSE } from "./useSSE";
import type { ChatMessage, ResearcherState, ChatAction, ChatTraceStep, ChatRuntimeTraceEvent } from "@/types";

let _msgId = 0;
function nextId() { return `msg-${++_msgId}`; }

export type ChatPhase = "idle" | "dispatching" | "researching" | "synthesizing";

interface ChatState {
  messages: ChatMessage[];
  researchers: Map<string, ResearcherState>;
  synthesis: string;
  actions: ChatAction[];
  processSteps: string[];
  traceSteps: ChatTraceStep[];
  runtimeTrace: ChatRuntimeTraceEvent[];
  activeQuestion: string | null;
  isLoading: boolean;
  phase: ChatPhase;
}

type Action =
  | { type: "USER_MESSAGE"; message: ChatMessage }
  | { type: "DISPATCH" }
  | { type: "RESEARCHER_START"; id: string; name: string }
  | { type: "RESEARCHER_CHUNK"; id: string; text: string }
  | { type: "RESEARCHER_DONE"; id: string }
  | { type: "SYNTHESIS_CHUNK"; text: string }
  | { type: "ACTIONS"; actions: ChatAction[] }
  | { type: "PROCESS_STEP"; step: string }
  | { type: "TRACE_STEP"; trace: ChatTraceStep }
  | { type: "RUNTIME_TRACE"; trace: ChatRuntimeTraceEvent }
  | { type: "DONE"; message: ChatMessage }
  | { type: "ERROR"; message: ChatMessage };

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "USER_MESSAGE":
      return {
        ...state,
        messages: [...state.messages, action.message],
        researchers: new Map(),
        synthesis: "",
        actions: [],
        processSteps: ["Lucas 收到问题"],
        traceSteps: [],
        runtimeTrace: [],
        activeQuestion: action.message.content,
        isLoading: true,
        phase: "dispatching",
      };
    case "DISPATCH":
      return { ...state, phase: "dispatching" };
    case "RESEARCHER_START": {
      const researchers = new Map(state.researchers);
      researchers.set(action.id, { id: action.id, name: action.name, status: "running", text: "" });
      return { ...state, researchers, phase: "researching" };
    }
    case "RESEARCHER_CHUNK": {
      const researchers = new Map(state.researchers);
      const r = researchers.get(action.id);
      if (r) researchers.set(action.id, { ...r, text: r.text + action.text });
      return { ...state, researchers };
    }
    case "RESEARCHER_DONE": {
      const researchers = new Map(state.researchers);
      const r = researchers.get(action.id);
      if (r) researchers.set(action.id, { ...r, status: "done" });
      return { ...state, researchers };
    }
    case "SYNTHESIS_CHUNK":
      return { ...state, synthesis: state.synthesis + action.text, phase: "synthesizing" };
    case "ACTIONS":
      return { ...state, actions: action.actions };
    case "PROCESS_STEP":
      if (!action.step || state.processSteps.at(-1) === action.step) return state;
      return { ...state, processSteps: [...state.processSteps, action.step] };
    case "TRACE_STEP":
      return { ...state, traceSteps: [...state.traceSteps, action.trace] };
    case "RUNTIME_TRACE":
      return state.runtimeTrace.at(-1)?.sequence === action.trace.sequence
        ? { ...state, runtimeTrace: [...state.runtimeTrace.slice(0, -1), action.trace] }
        : { ...state, runtimeTrace: [...state.runtimeTrace, action.trace] };
    case "DONE": {
      return {
        ...state,
        messages: [...state.messages, action.message],
        actions: [],
        isLoading: false,
        phase: "idle",
        activeQuestion: null,
      };
    }
    case "ERROR":
      return {
        ...state,
        messages: [...state.messages, action.message],
        isLoading: false,
        phase: "idle",
        actions: [],
        synthesis: "",
        activeQuestion: null,
      };
    default:
      return state;
  }
}

function createInitialState(messages: ChatMessage[]): ChatState {
  return {
    messages,
    researchers: new Map(),
    synthesis: "",
    actions: [],
    processSteps: [],
    traceSteps: [],
    runtimeTrace: [],
    activeQuestion: null,
    isLoading: false,
    phase: "idle",
  };
}

export function useChat(
  initialMessages: ChatMessage[],
  onMessagesCommitted: (messages: ChatMessage[]) => void,
  onResearchTarget?: (target: string) => void,
  onDone?: () => void,
) {
  const [state, dispatch] = useReducer(reducer, initialMessages, createInitialState);
  const { send } = useSSE();
  const abortRef = useRef<AbortController | null>(null);

  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    const errorMessage: ChatMessage = {
      id: nextId(),
      role: "assistant",
      content: "错误: 已取消",
      processSteps: [...stateRef.current.processSteps, "任务已取消"],
      traceSteps: [
        ...stateRef.current.traceSteps,
        { id: nextId(), kind: "action", label: "任务已取消", status: "error" },
      ],
      runtimeTrace: [
        ...stateRef.current.runtimeTrace,
        {
          sequence: stateRef.current.runtimeTrace.length + 1,
          timestamp: new Date().toISOString(),
          event: "run_finished",
          data: { finishReason: "cancelled" },
        },
      ],
    };
    const messages = [...stateRef.current.messages, errorMessage];
    dispatch({ type: "ERROR", message: errorMessage });
    onMessagesCommitted(messages);
  }, [onMessagesCommitted]);

  const sendMessage = useCallback(
    async (question: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const previousMessages = stateRef.current.messages;
      const userMessage: ChatMessage = { id: nextId(), role: "user", content: question };
      const streamedResearchers = new Map<string, ResearcherState>();
      let streamedSynthesis = "";
      let streamedActions: ChatAction[] = [];
      let streamedProcessSteps = ["Lucas 收到问题"];
      let streamedTraceSteps: ChatTraceStep[] = [];
      let streamedRuntimeTrace: ChatRuntimeTraceEvent[] = [];
      let completed = false;

      const appendProcessStep = (step: string) => {
        if (!step || streamedProcessSteps.at(-1) === step) return;
        streamedProcessSteps = [...streamedProcessSteps, step];
        dispatch({ type: "PROCESS_STEP", step });
      };

      const appendTraceStep = (trace: ChatTraceStep) => {
        streamedTraceSteps = [...streamedTraceSteps, trace];
        dispatch({ type: "TRACE_STEP", trace });
      };

      const appendRuntimeTrace = (
        event: string,
        data: Record<string, unknown>,
        step?: number,
      ) => {
        const previous = streamedRuntimeTrace.at(-1);
        if (event === "model_reasoning" && previous?.event === event && previous.step === step) {
          const trace: ChatRuntimeTraceEvent = {
            ...previous,
            data: {
              text: String(previous.data.text ?? "") + String(data.text ?? ""),
            },
          };
          streamedRuntimeTrace = [...streamedRuntimeTrace.slice(0, -1), trace];
          dispatch({ type: "RUNTIME_TRACE", trace });
          return;
        }
        const trace: ChatRuntimeTraceEvent = {
          sequence: streamedRuntimeTrace.length + 1,
          timestamp: new Date().toISOString(),
          event,
          ...(step === undefined ? {} : { step }),
          data,
        };
        streamedRuntimeTrace = [...streamedRuntimeTrace, trace];
        dispatch({ type: "RUNTIME_TRACE", trace });
      };


      dispatch({ type: "USER_MESSAGE", message: userMessage });
      appendRuntimeTrace("run_started", { question });

      const history = previousMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        await send(
          question,
          history,
          (event, data: unknown) => {
            const d = data as Record<string, string>;
            switch (event) {
              case "status":
                appendProcessStep(d.message);
                break;
              case "dispatch":
                appendProcessStep("Lucas 开始分析");
                dispatch({ type: "DISPATCH" });
                onResearchTarget?.(question);
                break;
              case "researcher_start":
                streamedResearchers.set(d.id, { id: d.id, name: d.name, status: "running", text: "" });
                dispatch({ type: "RESEARCHER_START", id: d.id, name: d.name });
                break;
              case "trace_event": {
                const trace = data as {
                  event: string;
                  step?: number;
                  data?: Record<string, unknown>;
                };
                appendRuntimeTrace(trace.event, trace.data ?? {}, trace.step);
                break;
              }
              case "summary": {
                const s = data as { step: number; text: string };
                if (s.text) {
                  appendRuntimeTrace("summary", { text: s.text }, s.step);
                  appendTraceStep({
                    id: nextId(),
                    kind: "summary",
                    label: s.text,
                    status: "done",
                    step: s.step,
                  });
                }
                break;
              }
              case "tool_step": {
                const toolStep = data as {
                  step: number;
                  tool: string;
                  args: Record<string, unknown>;
                  ok: boolean;
                  output: string;
                  message: string;
                };
                appendProcessStep(toolStep.message);
                appendRuntimeTrace("tool_call_finished", {
                  tool: toolStep.tool,
                  args: toolStep.args,
                  ok: toolStep.ok,
                  output: toolStep.output,
                }, toolStep.step);
                appendTraceStep({
                  id: nextId(),
                  kind: "tool",
                  label: toolStep.ok ? `Lucas 调用 ${toolStep.tool}` : `Lucas 调用 ${toolStep.tool} 失败`,
                  status: toolStep.ok ? "done" : "error",
                  step: toolStep.step,
                  tool: toolStep.tool,
                  input: toolStep.args,
                  output: toolStep.output,
                });
                break;
              }
              case "researcher_chunk":
                if (streamedResearchers.has(d.id)) {
                  const researcher = streamedResearchers.get(d.id)!;
                  streamedResearchers.set(d.id, { ...researcher, text: researcher.text + d.text });
                }
                dispatch({ type: "RESEARCHER_CHUNK", id: d.id, text: d.text });
                break;
              case "researcher_done":
                appendProcessStep("Lucas 完成分析");
                appendTraceStep({ id: nextId(), kind: "action", label: "Lucas 完成分析", status: "done" });
                if (streamedResearchers.has(d.id)) {
                  const researcher = streamedResearchers.get(d.id)!;
                  streamedResearchers.set(d.id, { ...researcher, status: "done" });
                }
                dispatch({ type: "RESEARCHER_DONE", id: d.id });
                break;
              case "synthesis_chunk":
                streamedSynthesis += d.text;
                dispatch({ type: "SYNTHESIS_CHUNK", text: d.text });
                break;
              case "actions":
                streamedActions = (data as { actions: ChatAction[] }).actions;
                dispatch({ type: "ACTIONS", actions: streamedActions });
                break;
              case "done": {
                completed = true;
                const done = data as { total_tokens?: number };
                appendRuntimeTrace("assistant_answer", { content: streamedSynthesis });
                appendRuntimeTrace("run_finished", {
                  finishReason: "completed",
                  totalTokens: done.total_tokens ?? 0,
                });
                const assistantMessage: ChatMessage = {
                  id: nextId(),
                  role: "assistant",
                  content: streamedSynthesis,
                  researchers: Array.from(streamedResearchers.values()),
                  synthesis: streamedSynthesis,
                  actions: streamedActions.length > 0 ? streamedActions : undefined,
                  processSteps: streamedProcessSteps,
                  traceSteps: streamedTraceSteps,
                  runtimeTrace: streamedRuntimeTrace,
                };
                const messages = [...previousMessages, userMessage, assistantMessage];
                dispatch({ type: "DONE", message: assistantMessage });
                onMessagesCommitted(messages);
                onDone?.();
                break;
              }
              case "error": {
                completed = true;
                appendProcessStep("处理失败");
                appendTraceStep({ id: nextId(), kind: "action", label: "Lucas 分析失败", status: "error" });
                appendRuntimeTrace("run_finished", {
                  finishReason: "error",
                  message: d.message,
                });
                const errorMessage: ChatMessage = {
                  id: nextId(),
                  role: "assistant",
                  content: `错误: ${d.message}`,
                  processSteps: streamedProcessSteps,
                  traceSteps: streamedTraceSteps,
                  runtimeTrace: streamedRuntimeTrace,
                };
                const messages = [...previousMessages, userMessage, errorMessage];
                dispatch({ type: "ERROR", message: errorMessage });
                onMessagesCommitted(messages);
                break;
              }
            }
          },
          controller.signal
        );
      } catch (e: unknown) {
        if (!completed && e instanceof Error && e.name !== "AbortError") {
          appendProcessStep("连接或处理失败");
          appendTraceStep({ id: nextId(), kind: "action", label: "连接或处理失败", status: "error" });
          appendRuntimeTrace("run_finished", {
            finishReason: "connection_error",
            message: e.message,
          });
          const errorMessage: ChatMessage = {
            id: nextId(),
            role: "assistant",
            content: `错误: ${e.message}`,
            processSteps: streamedProcessSteps,
            traceSteps: streamedTraceSteps,
            runtimeTrace: streamedRuntimeTrace,
          };
          const messages = [...previousMessages, userMessage, errorMessage];
          dispatch({ type: "ERROR", message: errorMessage });
          onMessagesCommitted(messages);
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [send, onMessagesCommitted, onResearchTarget, onDone]
  );

  return { state, sendMessage, cancel };
}

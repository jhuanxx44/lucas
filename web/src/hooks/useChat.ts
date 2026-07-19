import { useReducer, useCallback, useEffect, useRef } from "react";
import { useSSE } from "./useSSE";
import type { ChatMessage, ResearcherState, ChatAction } from "@/types";

let _msgId = 0;
function nextId() { return `msg-${++_msgId}`; }

export type ChatPhase = "idle" | "dispatching" | "researching" | "synthesizing";

interface ChatState {
  messages: ChatMessage[];
  researchers: Map<string, ResearcherState>;
  synthesis: string;
  actions: ChatAction[];
  processSteps: string[];
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
        processSteps: ["已收到问题"],
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
    case "DONE": {
      return {
        ...state,
        messages: [...state.messages, action.message],
        actions: [],
        isLoading: false,
        phase: "idle",
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
      let streamedProcessSteps = ["已收到问题"];
      let completed = false;

      const appendProcessStep = (step: string) => {
        if (!step || streamedProcessSteps.at(-1) === step) return;
        streamedProcessSteps = [...streamedProcessSteps, step];
        dispatch({ type: "PROCESS_STEP", step });
      };

      dispatch({ type: "USER_MESSAGE", message: userMessage });

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
                // single 模式：不再展示"选择研究员"步骤，dispatch 仅用于 wiki 联动定位
                dispatch({ type: "DISPATCH" });
                onResearchTarget?.(question);
                break;
              case "researcher_start":
                appendProcessStep(`${d.name}开始分析`);
                streamedResearchers.set(d.id, { id: d.id, name: d.name, status: "running", text: "" });
                dispatch({ type: "RESEARCHER_START", id: d.id, name: d.name });
                break;
              case "researcher_chunk":
                if (streamedResearchers.has(d.id)) {
                  const researcher = streamedResearchers.get(d.id)!;
                  streamedResearchers.set(d.id, { ...researcher, text: researcher.text + d.text });
                }
                dispatch({ type: "RESEARCHER_CHUNK", id: d.id, text: d.text });
                break;
              case "researcher_done":
                appendProcessStep(`${streamedResearchers.get(d.id)?.name ?? d.id}完成分析`);
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
                const assistantMessage: ChatMessage = {
                  id: nextId(),
                  role: "assistant",
                  content: streamedSynthesis,
                  researchers: Array.from(streamedResearchers.values()),
                  synthesis: streamedSynthesis,
                  actions: streamedActions.length > 0 ? streamedActions : undefined,
                  processSteps: streamedProcessSteps,
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
                const errorMessage: ChatMessage = {
                  id: nextId(),
                  role: "assistant",
                  content: `错误: ${d.message}`,
                  processSteps: streamedProcessSteps,
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
          const errorMessage: ChatMessage = {
            id: nextId(),
            role: "assistant",
            content: `错误: ${e.message}`,
            processSteps: streamedProcessSteps,
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

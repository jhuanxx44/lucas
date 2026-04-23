import { useReducer, useCallback, useRef } from "react";
import { useSSE } from "./useSSE";
import type { ChatMessage, ResearcherState } from "@/types";

let _msgId = 0;
function nextId() { return `msg-${++_msgId}`; }

export type ChatPhase = "idle" | "dispatching" | "researching" | "synthesizing";

interface ChatState {
  messages: ChatMessage[];
  researchers: Map<string, ResearcherState>;
  synthesis: string;
  isLoading: boolean;
  phase: ChatPhase;
}

type Action =
  | { type: "USER_MESSAGE"; question: string }
  | { type: "DISPATCH" }
  | { type: "RESEARCHER_START"; id: string; name: string }
  | { type: "RESEARCHER_CHUNK"; id: string; text: string }
  | { type: "RESEARCHER_DONE"; id: string }
  | { type: "SYNTHESIS_CHUNK"; text: string }
  | { type: "DONE" }
  | { type: "ERROR"; message: string };

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "USER_MESSAGE":
      return {
        ...state,
        messages: [...state.messages, { id: nextId(), role: "user", content: action.question }],
        researchers: new Map(),
        synthesis: "",
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
    case "DONE": {
      const assistantMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: state.synthesis,
        researchers: Array.from(state.researchers.values()),
        synthesis: state.synthesis,
      };
      return {
        ...state,
        messages: [...state.messages, assistantMsg],
        isLoading: false,
        phase: "idle",
      };
    }
    case "ERROR":
      return { ...state, isLoading: false, phase: "idle", synthesis: `错误: ${action.message}` };
    default:
      return state;
  }
}

const initialState: ChatState = {
  messages: [],
  researchers: new Map(),
  synthesis: "",
  isLoading: false,
  phase: "idle",
};

export function useChat(onResearchTarget?: (target: string) => void, onDone?: () => void) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { send } = useSSE();
  const abortRef = useRef<AbortController | null>(null);

  const stateRef = useRef(state);
  stateRef.current = state;

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    dispatch({ type: "ERROR", message: "已取消" });
  }, []);

  const sendMessage = useCallback(
    async (question: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      dispatch({ type: "USER_MESSAGE", question });

      const history = stateRef.current.messages.map((m) => ({
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
              case "dispatch":
                dispatch({ type: "DISPATCH" });
                onResearchTarget?.(question);
                break;
              case "researcher_start":
                dispatch({ type: "RESEARCHER_START", id: d.id, name: d.name });
                break;
              case "researcher_chunk":
                dispatch({ type: "RESEARCHER_CHUNK", id: d.id, text: d.text });
                break;
              case "researcher_done":
                dispatch({ type: "RESEARCHER_DONE", id: d.id });
                break;
              case "synthesis_chunk":
                dispatch({ type: "SYNTHESIS_CHUNK", text: d.text });
                break;
              case "done":
                dispatch({ type: "DONE" });
                onDone?.();
                break;
              case "error":
                dispatch({ type: "ERROR", message: d.message });
                break;
            }
          },
          controller.signal
        );
      } catch (e: unknown) {
        if (e instanceof Error && e.name !== "AbortError") {
          dispatch({ type: "ERROR", message: e.message });
        }
      }
    },
    [send, onResearchTarget, onDone]
  );

  return { state, sendMessage, cancel };
}

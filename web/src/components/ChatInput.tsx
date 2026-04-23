import { useState } from "react";
import { Send, Square } from "lucide-react";
import type { ChatPhase } from "@/hooks/useChat";

const PHASE_LABEL: Record<ChatPhase, string> = {
  idle: "",
  dispatching: "正在派发任务…",
  researching: "研究员分析中…",
  synthesizing: "正在综合分析…",
};

interface ChatInputProps {
  onSend: (message: string) => void;
  onCancel: () => void;
  phase: ChatPhase;
}

export function ChatInput({ onSend, onCancel, phase }: ChatInputProps) {
  const [text, setText] = useState("");
  const loading = phase !== "idle";

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setText("");
  };

  return (
    <div className="border-t border-zinc-200 dark:border-zinc-800 p-3">
      {loading && (
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500" />
          </span>
          <span className="text-xs text-zinc-500 dark:text-zinc-400">{PHASE_LABEL[phase]}</span>
        </div>
      )}
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder={loading ? "等待完成后可继续提问…" : "输入你的问题..."}
          disabled={loading}
          className="flex-1 bg-zinc-100 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
        />
        {loading ? (
          <button
            onClick={onCancel}
            className="bg-red-500/90 hover:bg-red-500 text-white rounded-lg px-3 py-2 transition-colors"
            title="取消"
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-300 dark:disabled:bg-zinc-700 text-white rounded-lg px-3 py-2 transition-colors"
          >
            <Send size={16} />
          </button>
        )}
      </div>
    </div>
  );
}

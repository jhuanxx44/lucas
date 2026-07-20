import { useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
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
  const composingRef = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const loading = phase !== "idle";

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setText("");
    if (inputRef.current) inputRef.current.style.height = "auto";
  };

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-white via-white/95 to-transparent px-3 pb-3 pt-10 dark:from-zinc-950 dark:via-zinc-950/95 sm:px-6 sm:pb-5">
      <div className="pointer-events-auto mx-auto w-full max-w-3xl">
        {loading && (
          <div className="mb-2 flex items-center gap-2 px-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500" />
            </span>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">{PHASE_LABEL[phase]}</span>
          </div>
        )}
        <div className="flex items-end gap-2 rounded-2xl border border-zinc-200 bg-white p-2 shadow-[0_8px_30px_rgba(24,24,27,0.08)] transition-colors focus-within:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-900 dark:shadow-[0_8px_30px_rgba(0,0,0,0.28)] dark:focus-within:border-zinc-500">
          <textarea
            ref={inputRef}
            rows={1}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              e.currentTarget.style.height = "auto";
              e.currentTarget.style.height = `${Math.min(e.currentTarget.scrollHeight, 160)}px`;
            }}
            onCompositionStart={() => { composingRef.current = true; }}
            onCompositionEnd={() => { composingRef.current = false; }}
            onKeyDown={(e) => {
              if (e.key !== "Enter" || e.shiftKey) return;
              if (e.nativeEvent.isComposing || composingRef.current || e.nativeEvent.keyCode === 229) return;
              e.preventDefault();
              handleSend();
            }}
            placeholder={loading ? "等待 Lucas 完成当前分析" : "给 Lucas 发送消息"}
            disabled={loading}
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-zinc-800 outline-none placeholder:text-zinc-400 disabled:opacity-50 dark:text-zinc-100 dark:placeholder:text-zinc-500"
          />
          {loading ? (
            <button
              onClick={onCancel}
              aria-label="停止生成"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-zinc-900 text-white transition-colors hover:bg-zinc-700 active:scale-95 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
              title="取消"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!text.trim()}
              aria-label="发送消息"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-zinc-900 text-white transition-colors hover:bg-zinc-700 active:scale-95 disabled:bg-zinc-200 disabled:text-zinc-400 disabled:active:scale-100 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white dark:disabled:bg-zinc-800 dark:disabled:text-zinc-600"
            >
              <ArrowUp size={17} strokeWidth={2.2} />
            </button>
          )}
        </div>
        <p className="mt-2 text-center text-[11px] text-zinc-400 dark:text-zinc-600">Enter 发送，Shift+Enter 换行</p>
      </div>
    </div>
  );
}

import { useState, useRef } from "react";
import { Send, Square, ChevronDown } from "lucide-react";
import type { ChatPhase } from "@/hooks/useChat";

const PHASE_LABEL: Record<ChatPhase, string> = {
  idle: "",
  dispatching: "Lucas 开始调研…",
  researching: "Lucas 调研中…",
  synthesizing: "正在生成回答…",
};

const MODELS = [
  { label: "Flash", value: "deepseek-v4-flash" },
  { label: "Pro", value: "deepseek-v4-pro" },
] as const;

interface ChatInputProps {
  onSend: (message: string, model?: string) => void;
  onCancel: () => void;
  phase: ChatPhase;
}

export function ChatInput({ onSend, onCancel, phase }: ChatInputProps) {
  const [text, setText] = useState("");
  const [model, setModel] = useState<string>("deepseek-v4-flash");
  const [modelOpen, setModelOpen] = useState(false);
  const loading = phase !== "idle";
  const isComposingRef = useRef(false);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    onSend(trimmed, model);
    setText("");
  };

  const currentLabel = MODELS.find((m) => m.value === model)?.label ?? "Flash";

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
      <div className="flex gap-2 items-end">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onCompositionStart={() => { isComposingRef.current = true; }}
          onCompositionEnd={() => {
            // delay reset: compositionend fires before keydown(Enter),
            // so the Enter keydown must still see isComposing = true
            setTimeout(() => { isComposingRef.current = false; }, 0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !isComposingRef.current) handleSend();
          }}
          placeholder={loading ? "等待完成后可继续提问…" : "输入你的问题..."}
          disabled={loading}
          className="flex-1 bg-zinc-100 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
        />
        {loading ? (
          <button
            onClick={onCancel}
            className="bg-red-500/90 hover:bg-red-500 text-white rounded-lg px-3 py-2 transition-colors shrink-0"
            title="取消"
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-300 dark:disabled:bg-zinc-700 text-white rounded-lg px-3 py-2 transition-colors shrink-0"
          >
            <Send size={16} />
          </button>
        )}
        <div className="relative shrink-0">
          <button
            onClick={() => setModelOpen((o) => !o)}
            className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300 px-2 py-2 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            title="切换模型"
          >
            <span className="font-mono">{currentLabel}</span>
            <ChevronDown size={12} className={`transition-transform ${modelOpen ? "rotate-180" : ""}`} />
          </button>
          {modelOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setModelOpen(false)} />
              <div className="absolute bottom-full right-0 mb-1 z-20 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg shadow-lg py-1 min-w-[100px]">
                {MODELS.map((m) => (
                  <button
                    key={m.value}
                    onClick={() => { setModel(m.value); setModelOpen(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors ${m.value === model ? "text-indigo-600 dark:text-indigo-400 font-medium" : "text-zinc-600 dark:text-zinc-400"}`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

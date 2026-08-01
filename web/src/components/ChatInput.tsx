import { useState, useRef, useCallback } from "react";
import { Send, Square, ChevronDown } from "lucide-react";
import type { ChatPhase } from "@/hooks/useChat";

const MODELS = [
  { label: "Flash", value: "deepseek-v4-flash" },
  { label: "Pro", value: "deepseek-v4-pro" },
] as const;

// 输入法组合结束后的一小段时间内仍可能到达“提交组合”的回车 keydown
// （部分浏览器跨任务派发，compositionend 先于 keydown 到达）。
// 该窗口内不发送消息；不要改回 onCompositionEnd + setTimeout(0) 复位，
// 否则会回归中文输入法按回车误发送 bug。
const COMPOSITION_END_GUARD_MS = 300;

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
  const compositionEndRef = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }, []);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    onSend(trimmed, model);
    setText("");
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    });
  };

  const currentLabel = MODELS.find((m) => m.value === model)?.label ?? "Flash";

  return (
    <div className="border-t border-zinc-200 dark:border-zinc-800 p-3">
      <div className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg focus-within:border-indigo-500 transition-colors">
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            adjustHeight();
          }}
          onCompositionStart={() => { isComposingRef.current = true; }}
          onCompositionEnd={() => {
            isComposingRef.current = false;
            compositionEndRef.current = Date.now();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              const composing =
                isComposingRef.current ||
                e.nativeEvent.isComposing ||
                e.nativeEvent.keyCode === 229;
              const compositionJustEnded =
                Date.now() - compositionEndRef.current < COMPOSITION_END_GUARD_MS;
              if (composing || compositionJustEnded) return;
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={loading ? "等待完成后可继续提问…" : "输入你的问题"}
          disabled={loading}
          className="w-full bg-transparent px-4 pt-3 pb-1.5 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:outline-none disabled:opacity-50 overflow-x-hidden break-words resize-none"
        />
        <div className="flex items-center justify-between px-2.5 pb-2.5">
          <div className="relative">
            <button
              onClick={() => setModelOpen((o) => !o)}
              className="flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 rounded-md px-2 py-1 transition-colors"
              title="切换模型"
            >
              <span className="font-medium">{currentLabel}</span>
              <ChevronDown size={10} className={`transition-transform ${modelOpen ? "rotate-180" : ""}`} />
            </button>
            {modelOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setModelOpen(false)} />
                <div className="absolute bottom-full left-0 mb-1 z-20 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg shadow-lg py-1 min-w-[100px]">
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
          {loading ? (
            <button
              onClick={onCancel}
              className="bg-red-500/90 hover:bg-red-500 text-white rounded-md p-1.5 transition-colors"
              title="取消"
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!text.trim()}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-300 dark:disabled:bg-zinc-700 text-white rounded-md p-1.5 transition-colors"
            >
              <Send size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

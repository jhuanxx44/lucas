import { useState, useRef, useCallback, useEffect } from "react";
import { Send, Square, ChevronDown, Clock, X } from "lucide-react";
import type { ChatPhase } from "@/hooks/useChat";
import { formatTokens } from "@/hooks/useChat";
import type { ChatContextCompression, ChatContextUsage, PendingTask } from "@/types";

const MODELS = [
  { label: "Flash", value: "deepseek-v4-flash" },
  { label: "Pro", value: "deepseek-v4-pro" },
] as const;

// 输入法组合结束后的一小段时间内仍可能到达“提交组合”的回车 keydown
// （Firefox/Safari 跨任务派发，compositionend 先于 keydown 到达）。
// 该窗口只吞掉“提交组合键”本身：窗口内第一次回车被吞后立即解除，
// 组合若是由回车 keydown 提交的（Chrome 顺序）则直接解除窗口，
// 避免把用户紧接着的发送回车吞成换行。
const COMPOSITION_END_GUARD_MS = 100;
const CONTEXT_LIMIT_DEFAULT = 1_000_000;

function ContextRing({ usage, lastCompression }: { usage: ChatContextUsage | null; lastCompression: ChatContextCompression | null }) {
  // 压缩发生时圆环做一次脉冲高亮，明确"环回退是主动压缩而非数据错误"
  const [pulse, setPulse] = useState(false);
  const pulseTimerRef = useRef<number | null>(null);
  useEffect(() => {
    if (!lastCompression) return;
    setPulse(true);
    if (pulseTimerRef.current !== null) window.clearTimeout(pulseTimerRef.current);
    pulseTimerRef.current = window.setTimeout(() => setPulse(false), 1800);
    return () => {
      if (pulseTimerRef.current !== null) window.clearTimeout(pulseTimerRef.current);
    };
  }, [lastCompression?.step, lastCompression?.beforeTokens]);
  // 无数据或真实用量为 0 时隐藏圆环
  if (!usage || usage.promptTokens <= 0) return null;
  const limit = usage.contextLimit || CONTEXT_LIMIT_DEFAULT;
  const used = Math.min(usage.promptTokens, limit);
  const ratio = limit > 0 ? used / limit : 0;
  const radius = 8;
  const circumference = 2 * Math.PI * radius;
  const strokeClass = ratio >= 0.9
    ? "stroke-red-500"
    : ratio >= 0.7
      ? "stroke-amber-500"
      : "stroke-indigo-500";
  const baseLabel = `Context 使用：${used.toLocaleString()} / ${limit.toLocaleString()} tokens（${(ratio * 100).toFixed(1)}%）`;
  const compressionNote = lastCompression
    ? `；最近压缩：第 ${lastCompression.step} 步，丢弃 ${lastCompression.droppedSteps.length} 步内容，释放约 ${formatTokens(lastCompression.freedTokens)} tokens`
    : "";
  const label = `${baseLabel}${compressionNote}`;

  return (
    <div className="flex items-center gap-1.5" title={label}>
      <svg
        width="22"
        height="22"
        viewBox="0 0 22 22"
        className={`shrink-0 rounded-full ${pulse ? "animate-pulse ring-2 ring-amber-400/50" : ""}`}
      >
        <circle
          cx="11"
          cy="11"
          r={radius}
          fill="none"
          strokeWidth="2.5"
          className="stroke-zinc-200 dark:stroke-zinc-700"
        />
        <circle
          cx="11"
          cy="11"
          r={radius}
          fill="none"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          transform="rotate(-90 11 11)"
          className={`transition-all duration-300 ${strokeClass}`}
        />
      </svg>
      {pulse && (
        <span className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-medium text-amber-600 dark:bg-amber-500/15 dark:text-amber-400">
          压缩
        </span>
      )}
    </div>
  );
}

interface ChatInputProps {
  onSend: (message: string, model?: string) => void;
  onCancel: () => void;
  onRemovePending: (id: string) => void;
  phase: ChatPhase;
  contextUsage: ChatContextUsage | null;
  lastCompression: ChatContextCompression | null;
  pendingQueue: PendingTask[];
}

export function ChatInput({ onSend, onCancel, onRemovePending, phase, contextUsage, lastCompression, pendingQueue }: ChatInputProps) {
  const [text, setText] = useState("");
  const [model, setModel] = useState<string>("deepseek-v4-flash");
  const [modelOpen, setModelOpen] = useState(false);
  const loading = phase !== "idle";
  const isComposingRef = useRef(false);
  const compositionEndRef = useRef(0);
  // 组合由回车 keydown 提交（Chrome：keydown(Enter, isComposing) 先于 compositionend）
  const enterCommitRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }, []);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
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
      <div className="mx-auto w-full max-w-[46rem] rounded-2xl border border-zinc-200 bg-white shadow-sm transition-shadow focus-within:border-indigo-300 focus-within:shadow-md focus-within:ring-2 focus-within:ring-indigo-500/15 dark:border-zinc-700 dark:bg-zinc-900 dark:focus-within:border-indigo-500/50 dark:focus-within:ring-indigo-400/15">
        {pendingQueue.length > 0 && (
          <div className="space-y-1 px-3 pt-2.5">
            <div className="text-[10px] font-medium tracking-wide text-zinc-400 dark:text-zinc-500">
              排队中 {pendingQueue.length}
            </div>
            {pendingQueue.map((task) => (
              <div
                key={task.id}
                className="flex items-center gap-1.5 rounded-md bg-zinc-100 py-1 pl-2 pr-1 dark:bg-zinc-800"
                title={task.question}
              >
                <Clock size={11} className="shrink-0 text-zinc-400 dark:text-zinc-500" />
                <span className="min-w-0 flex-1 truncate text-xs text-zinc-600 dark:text-zinc-300">
                  {task.question}
                </span>
                <button
                  onClick={() => onRemovePending(task.id)}
                  title="移除排队任务"
                  className="shrink-0 rounded p-0.5 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-600 dark:hover:bg-zinc-700 dark:hover:text-zinc-200 transition-colors"
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={textareaRef}
          rows={1}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            adjustHeight();
          }}
          onCompositionStart={() => {
            isComposingRef.current = true;
            enterCommitRef.current = false;
          }}
          onCompositionEnd={() => {
            isComposingRef.current = false;
            // Chrome 中组合由回车 keydown 提交时，该 keydown 已经处理过，
            // compositionend 之后不会再补发“提交组合”的回车，无需保留短窗口。
            if (enterCommitRef.current) {
              compositionEndRef.current = 0;
            } else {
              compositionEndRef.current = Date.now();
            }
            enterCommitRef.current = false;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              const composing =
                isComposingRef.current ||
                e.nativeEvent.isComposing ||
                e.nativeEvent.keyCode === 229;
              if (composing) {
                enterCommitRef.current = true;
                return; // 组合进行中：回车交给输入法提交，不拦截默认行为
              }
              e.preventDefault();
              const compositionJustEnded =
                Date.now() - compositionEndRef.current < COMPOSITION_END_GUARD_MS;
              if (compositionJustEnded) {
                // 可能是 Firefox/Safari 迟到的“提交组合”回车：吞掉且只吞这一次
                compositionEndRef.current = 0;
                return;
              }
              handleSend();
            }
          }}
          placeholder={loading ? "回复中，可继续输入下一个任务（将排队执行）…" : "输入你的问题"}
          className="w-full bg-transparent px-4 pt-3 pb-1.5 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 focus:outline-none overflow-x-hidden break-words resize-none"
        />
        <div className="flex items-center justify-between px-2.5 pb-2.5">
          <div className="flex items-center gap-2">
            <ContextRing usage={contextUsage} lastCompression={lastCompression} />
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
          </div>
          <div className="flex items-center gap-2">
            {loading ? (
              <button
                onClick={onCancel}
                className="bg-red-500/90 hover:bg-red-500 text-white rounded-full p-2 transition-colors"
                title="取消当前任务并清空排队"
              >
                <Square size={14} />
              </button>
            ) : null}
            <button
              onClick={handleSend}
              disabled={!text.trim()}
              title={loading ? "发送（当前任务完成后自动执行）" : "发送"}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-zinc-200 dark:disabled:bg-zinc-700 text-white disabled:text-zinc-400 dark:disabled:text-zinc-500 rounded-full p-2 transition-colors"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

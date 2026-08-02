import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Check, Copy } from "lucide-react";
import type { ChatMessage as ChatMessageType, ChatTraceStep } from "@/types";
import { AnalysisProcess } from "./AnalysisProcess";
import { REMARK_PLUGINS } from "@/lib/markdown";

// 正文的排版类与直播上屏块（ChatPanel streaming-answer）共用，
// 保证 DONE 提交消息时样式无缝衔接
export const PROSE_CLASSES = "prose prose-zinc max-w-none text-sm leading-7 tabular-nums dark:prose-invert prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-h4:text-sm prose-headings:font-semibold prose-headings:tracking-tight prose-p:my-4 prose-p:leading-7 prose-p:text-zinc-700 prose-a:text-indigo-600 prose-strong:text-zinc-900 prose-li:my-1 prose-li:text-zinc-700 prose-pre:rounded-xl prose-pre:border prose-pre:border-zinc-800 prose-pre:bg-zinc-950 dark:prose-p:text-zinc-300 dark:prose-a:text-indigo-400 dark:prose-strong:text-zinc-100 dark:prose-li:text-zinc-300";

interface Props {
  message: ChatMessageType;
  onAction?: (value: string) => void;
  // 刚流式完成的消息：分析过程默认展开，与直播态的视觉位置连续
  defaultOpen?: boolean;
}

// 历史消息只有 processSteps（无 traceSteps）时，退化成 action 步展示
function legacySteps(message: ChatMessageType): ChatTraceStep[] {
  return (message.processSteps ?? []).map((label, index) => ({
    id: `${message.id}-legacy-${index}`,
    kind: "action" as const,
    label,
    status: label.includes("失败") || label.includes("取消") ? "error" : "done",
  }));
}

// 极简复制按钮：点击复制本轮回答全文（原始 markdown），短暂反馈后复原
function CopyAnswerButton({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={handleCopy}
      title={copied ? "已复制" : "复制回答"}
      className="inline-flex items-center rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-600 dark:text-zinc-500 dark:hover:bg-zinc-900 dark:hover:text-zinc-300"
      aria-label={copied ? "已复制" : "复制回答"}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
}

export function ChatMessage({ message, onAction, defaultOpen = false }: Props) {
  if (message.role === "user") {
    return (
      <div className="animate-message-in mb-8 flex justify-end">
        <div className="max-w-[88%] rounded-2xl rounded-br-md bg-zinc-100 px-4 py-2.5 text-[15px] leading-6 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100 sm:max-w-[80%]">
          <span className="whitespace-pre-wrap">{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-message-in mb-10">
      <AnalysisProcess steps={message.traceSteps?.length ? message.traceSteps : legacySteps(message)} defaultOpen={defaultOpen} />
      <div className={PROSE_CLASSES}>
        <ReactMarkdown remarkPlugins={REMARK_PLUGINS}>
          {message.content}
        </ReactMarkdown>
      </div>
      {message.actions && message.actions.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {message.actions.map((action) => (
            <button
              key={action.value}
              onClick={() => onAction?.(action.value)}
              className="rounded-xl border border-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-50 active:scale-[0.98] dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
      {message.content && (
        <div className="mt-2">
          <CopyAnswerButton content={message.content} />
        </div>
      )}
    </div>
  );
}

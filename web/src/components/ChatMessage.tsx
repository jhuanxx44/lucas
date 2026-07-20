import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType } from "@/types";
import { AnalysisProcess } from "./AnalysisProcess";

interface Props {
  message: ChatMessageType;
  onAction?: (value: string) => void;
}

export function ChatMessage({ message, onAction }: Props) {
  if (message.role === "user") {
    return (
      <div className="mb-8 flex justify-end">
        <div className="max-w-[88%] rounded-2xl rounded-br-md bg-zinc-100 px-4 py-2.5 text-[15px] leading-6 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100 sm:max-w-[80%]">
          <span className="whitespace-pre-wrap">{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-10">
      <AnalysisProcess steps={message.processSteps ?? []} />
      <div className="prose prose-zinc max-w-none text-[15px] leading-7 dark:prose-invert prose-headings:font-semibold prose-headings:tracking-tight prose-p:my-4 prose-p:leading-7 prose-p:text-zinc-700 prose-a:text-indigo-600 prose-strong:text-zinc-900 prose-li:my-1 prose-li:text-zinc-700 prose-pre:rounded-xl prose-pre:border prose-pre:border-zinc-800 prose-pre:bg-zinc-950 dark:prose-p:text-zinc-300 dark:prose-a:text-indigo-400 dark:prose-strong:text-zinc-100 dark:prose-li:text-zinc-300">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
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
    </div>
  );
}

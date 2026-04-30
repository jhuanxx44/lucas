import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType } from "@/types";

interface Props {
  message: ChatMessageType;
  onAction?: (value: string) => void;
}

export function ChatMessage({ message, onAction }: Props) {
  if (message.role === "user") {
    return (
      <div className="bg-indigo-50 dark:bg-indigo-500/10 rounded-lg px-3 py-2 mb-3">
        <span className="text-sm text-indigo-700 dark:text-indigo-300">{message.content}</span>
      </div>
    );
  }

  return (
    <div className="mb-3">
      <div className="text-sm prose prose-sm max-w-none dark:prose-invert prose-p:text-zinc-600 dark:prose-p:text-zinc-300">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>
      </div>
      {message.actions && message.actions.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-2">
          {message.actions.map((action) => (
            <button
              key={action.value}
              onClick={() => onAction?.(action.value)}
              className="px-3 py-1.5 text-xs rounded-lg border border-indigo-200 dark:border-indigo-500/30 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 hover:border-indigo-300 dark:hover:border-indigo-500/50 transition-colors"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

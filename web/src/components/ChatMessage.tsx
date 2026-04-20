import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType } from "@/types";

export function ChatMessage({ message }: { message: ChatMessageType }) {
  if (message.role === "user") {
    return (
      <div className="bg-indigo-50 dark:bg-indigo-500/10 rounded-lg px-3 py-2 mb-3">
        <span className="text-sm text-indigo-700 dark:text-indigo-300">{message.content}</span>
      </div>
    );
  }

  return (
    <div className="mb-3 text-sm prose prose-sm max-w-none dark:prose-invert prose-p:text-zinc-600 dark:prose-p:text-zinc-300">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {message.content}
      </ReactMarkdown>
    </div>
  );
}

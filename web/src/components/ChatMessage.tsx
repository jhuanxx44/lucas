import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as ChatMessageType } from "@/types";

export function ChatMessage({ message }: { message: ChatMessageType }) {
  if (message.role === "user") {
    return (
      <div className="bg-indigo-500/10 rounded-lg px-3 py-2 mb-3">
        <span className="text-sm text-indigo-300">{message.content}</span>
      </div>
    );
  }

  return (
    <div className="mb-3 text-sm prose prose-invert prose-sm max-w-none prose-p:text-zinc-300">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {message.content}
      </ReactMarkdown>
    </div>
  );
}

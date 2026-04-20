import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Loader2 } from "lucide-react";

interface SynthesisCardProps {
  text: string;
  loading: boolean;
}

export function SynthesisCard({ text, loading }: SynthesisCardProps) {
  if (!text && !loading) return null;

  return (
    <div className="border border-indigo-300/40 dark:border-indigo-500/30 rounded-lg overflow-hidden mt-2">
      <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 dark:bg-indigo-500/10">
        <span>🧠</span>
        <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">综合分析</span>
        {loading && <Loader2 size={12} className="animate-spin text-indigo-500 dark:text-indigo-400 ml-auto" />}
      </div>
      {text && (
        <div className="px-3 pb-3 pt-1 text-sm prose prose-sm max-w-none dark:prose-invert prose-p:text-zinc-600 dark:prose-p:text-zinc-300 prose-headings:text-zinc-800 dark:prose-headings:text-zinc-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {text}
          </ReactMarkdown>
        </div>
      )}
      {!text && loading && (
        <div className="px-3 py-2 text-xs text-zinc-400 dark:text-zinc-500">等待研究员完成...</div>
      )}
    </div>
  );
}

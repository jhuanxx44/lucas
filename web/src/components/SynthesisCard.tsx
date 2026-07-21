import ReactMarkdown from "react-markdown";
import { Loader2 } from "lucide-react";
import { REMARK_PLUGINS } from "@/lib/markdown";

interface SynthesisCardProps {
  text: string;
  loading: boolean;
}

export function SynthesisCard({ text, loading }: SynthesisCardProps) {
  if (!text && !loading) return null;

  return (
    <div className="mt-4 border-l border-zinc-200 pl-4 dark:border-zinc-800">
      <div className="flex items-center gap-2 py-1 text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {loading && <Loader2 size={12} className="animate-spin" />}
        <span>{loading ? "Lucas 正在整理结论" : "Lucas 的结论"}</span>
      </div>
      {text && (
        <div className="prose prose-zinc mt-3 max-w-none text-[15px] dark:prose-invert prose-p:leading-7 prose-p:text-zinc-700 dark:prose-p:text-zinc-300">
          <ReactMarkdown remarkPlugins={REMARK_PLUGINS}>
            {text}
          </ReactMarkdown>
        </div>
      )}
      {!text && loading && (
        <div className="py-2 text-xs text-zinc-400 dark:text-zinc-500">正在等待分析结果</div>
      )}
    </div>
  );
}

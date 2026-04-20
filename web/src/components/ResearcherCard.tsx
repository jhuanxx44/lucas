import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import type { ResearcherState } from "@/types";

const ICONS: Record<string, string> = {
  fundamental: "📊",
  technical: "📈",
  macro: "🌐",
};

export function ResearcherCard({ researcher }: { researcher: ResearcherState }) {
  const [expanded, setExpanded] = useState(true);
  const icon = ICONS[researcher.id] || "📋";

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden mb-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-zinc-800/50 transition-colors"
      >
        <span>{icon}</span>
        <span className="font-medium text-zinc-200">{researcher.name}</span>
        <span className="ml-auto flex items-center gap-1">
          {researcher.status === "running" ? (
            <Loader2 size={12} className="animate-spin text-indigo-400" />
          ) : (
            <span className="text-green-400 text-xs">✓</span>
          )}
        </span>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {expanded && researcher.text && (
        <div className="px-3 pb-3 text-xs prose prose-invert prose-sm max-w-none prose-p:text-zinc-400 prose-headings:text-zinc-300">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {researcher.text}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}

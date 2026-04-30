import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { fetchRawReport } from "@/lib/api";
import type { WikiPage } from "@/types";

interface RawReportPanelProps {
  sources: unknown;
  researchers: unknown;
}

interface ReportState {
  path: string;
  label: string;
  page: WikiPage | null;
  loading: boolean;
  error: string | null;
  expanded: boolean;
}

function parseResearcherLabel(path: string, researchersStr: string | null): string {
  const filename = path.split("/").pop() ?? path;
  const id = filename.split("_")[0];
  if (researchersStr) {
    const match = researchersStr.match(new RegExp(`([^,]*${id}[^,]*)`, "i"));
    if (match) return match[1].trim();
  }
  return id;
}

export function RawReportPanel({ sources, researchers }: RawReportPanelProps) {
  const paths = Array.isArray(sources)
    ? (sources as string[]).filter((s) => typeof s === "string" && s.startsWith("raw/") && !s.startsWith("raw/sources/"))
    : [];

  const [reports, setReports] = useState<ReportState[]>(() =>
    paths.map((path) => ({
      path,
      label: parseResearcherLabel(path, typeof researchers === "string" ? researchers : null),
      page: null,
      loading: false,
      error: null,
      expanded: false,
    }))
  );

  if (paths.length === 0) return null;

  const toggle = async (index: number) => {
    setReports((prev) => {
      const next = [...prev];
      const r = { ...next[index] };
      r.expanded = !r.expanded;
      if (r.expanded && !r.page && !r.loading) {
        r.loading = true;
        fetchRawReport(r.path)
          .then((page) => {
            const label = typeof page.frontmatter?.researcher === "string" ? page.frontmatter.researcher : r.label;
            setReports((p) => p.map((x, i) => (i === index ? { ...x, page, label, loading: false } : x)));
          })
          .catch((e) => setReports((p) => p.map((x, i) => (i === index ? { ...x, error: e.message, loading: false } : x))));
      }
      next[index] = r;
      return next;
    });
  };

  return (
    <div className="mt-6 border-t border-zinc-200 dark:border-zinc-800 pt-4">
      <h3 className="text-sm font-semibold text-zinc-600 dark:text-zinc-400 mb-3">研究员原始报告</h3>
      <div className="space-y-2">
        {reports.map((r, i) => (
          <div key={r.path} className="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
            >
              {r.expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span className="font-medium text-zinc-700 dark:text-zinc-300">{r.label}</span>
              {r.loading && <Loader2 size={12} className="animate-spin text-indigo-500 ml-auto" />}
              {r.page?.frontmatter?.confidence ? (
                <span className={`ml-auto text-xs px-1.5 py-0.5 rounded-full ${
                  r.page.frontmatter.confidence === "high" ? "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400" :
                  r.page.frontmatter.confidence === "medium" ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-400" :
                  "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400"
                }`}>
                  {String(r.page.frontmatter.confidence)}
                </span>
              ) : null}
              {r.page?.frontmatter?.model ? (
                <span className="text-xs text-zinc-400 dark:text-zinc-500">
                  {String(r.page.frontmatter.model)}
                </span>
              ) : null}
            </button>
            {r.expanded && (
              <div className="px-3 pb-3">
                {r.error && <div className="text-xs text-red-500">{r.error}</div>}
                {r.page && (
                  <div className="text-sm prose prose-sm max-w-none dark:prose-invert prose-p:text-zinc-500 dark:prose-p:text-zinc-400 prose-headings:text-zinc-700 dark:prose-headings:text-zinc-300">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{r.page.content}</ReactMarkdown>
                  </div>
                )}
                {r.loading && !r.page && <div className="text-xs text-zinc-400">加载中...</div>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
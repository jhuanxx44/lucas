import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Minus, Plus } from "lucide-react";
import { fetchWikiPage, fetchRawFile, searchWiki } from "@/lib/api";
import { processWikiLinks } from "@/lib/markdown";
import { useWikiNavigation } from "@/hooks/useWikiNavigation";
import { RawReportPanel } from "@/components/RawReportPanel";
import type { WikiPage } from "@/types";

const FONT_SIZES = [12, 13, 14, 15, 16, 18, 20] as const;
const DEFAULT_INDEX = 2; // 14px

export function WikiContent() {
  const { currentPath, navigateTo } = useWikiNavigation();
  const [page, setPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [fontIndex, setFontIndex] = useState(DEFAULT_INDEX);

  useEffect(() => {
    if (!currentPath) return;
    setLoading(true);
    const isRaw = currentPath.startsWith("__raw__/");
    const fetcher = isRaw
      ? fetchRawFile(currentPath.replace("__raw__/", ""))
      : fetchWikiPage(currentPath);
    fetcher
      .then(setPage)
      .catch(() => setPage(null))
      .finally(() => setLoading(false));
  }, [currentPath]);

  if (!currentPath) {
    return <div className="text-zinc-400 dark:text-zinc-500 text-sm">选择左侧 wiki 页面查看内容</div>;
  }
  if (loading) {
    return <div className="text-zinc-400 dark:text-zinc-500 text-sm">加载中...</div>;
  }
  if (!page) {
    return <div className="text-red-500 dark:text-red-400 text-sm">页面加载失败</div>;
  }

  const fm = page.frontmatter;
  const tags = Array.isArray(fm.tags) ? (fm.tags as string[]) : [];
  const confidence = typeof fm.confidence === "string" ? fm.confidence : null;
  const updated = fm.updated != null ? String(fm.updated) : null;
  const processed = processWikiLinks(page.content);

  const btnClass = "text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 p-1 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-30 disabled:pointer-events-none";

  return (
    <div className="max-w-none">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-0.5 mr-2">
          <button onClick={() => setFontIndex((i) => i - 1)} disabled={fontIndex <= 0} className={btnClass} title="缩小字体">
            <Minus size={14} />
          </button>
          <span className="text-xs text-zinc-400 dark:text-zinc-500 w-7 text-center select-none">{FONT_SIZES[fontIndex]}</span>
          <button onClick={() => setFontIndex((i) => i + 1)} disabled={fontIndex >= FONT_SIZES.length - 1} className={btnClass} title="放大字体">
            <Plus size={14} />
          </button>
        </div>
        {tags.map((tag) => (
          <span key={tag} className="text-xs bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300 px-2 py-0.5 rounded-full">
            {tag}
          </span>
        ))}
        {confidence && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            confidence === "high" ? "bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400" :
            confidence === "medium" ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-400" :
            "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400"
          }`}>
            {confidence}
          </span>
        )}
        {updated && (
          <span className="text-xs text-zinc-400 dark:text-zinc-500">更新: {updated}</span>
        )}
      </div>
      <article style={{ fontSize: `${FONT_SIZES[fontIndex]}px` }} className="prose max-w-none dark:prose-invert prose-headings:text-zinc-800 dark:prose-headings:text-zinc-200 prose-p:text-zinc-600 dark:prose-p:text-zinc-300 prose-a:text-indigo-600 dark:prose-a:text-indigo-400 prose-strong:text-zinc-800 dark:prose-strong:text-zinc-200 prose-code:text-indigo-600 dark:prose-code:text-indigo-300 prose-td:text-zinc-600 dark:prose-td:text-zinc-300 prose-th:text-zinc-800 dark:prose-th:text-zinc-200">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              if (href?.startsWith("#wiki:")) {
                const target = href.replace("#wiki:", "");
                return (
                  <button
                    onClick={async () => {
                      const results = await searchWiki(target);
                      if (results.length > 0) {
                        navigateTo(results[0].path);
                      }
                    }}
                    className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 underline"
                  >
                    {children}
                  </button>
                );
              }
              return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
            },
          }}
        >
          {processed}
        </ReactMarkdown>
      </article>
      <RawReportPanel sources={fm.sources} researchers={fm.researchers} />
    </div>
  );
}

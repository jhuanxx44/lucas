import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchWikiPage, searchWiki } from "@/lib/api";
import { processWikiLinks } from "@/lib/markdown";
import { useWikiNavigation } from "@/hooks/useWikiNavigation";
import type { WikiPage } from "@/types";

export function WikiContent() {
  const { currentPath, navigateTo } = useWikiNavigation();
  const [page, setPage] = useState<WikiPage | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!currentPath) return;
    setLoading(true);
    fetchWikiPage(currentPath)
      .then(setPage)
      .catch(() => setPage(null))
      .finally(() => setLoading(false));
  }, [currentPath]);

  if (!currentPath) {
    return <div className="text-zinc-500 text-sm">选择左侧 wiki 页面查看内容</div>;
  }
  if (loading) {
    return <div className="text-zinc-500 text-sm">加载中...</div>;
  }
  if (!page) {
    return <div className="text-red-400 text-sm">页面加载失败</div>;
  }

  const fm = page.frontmatter;
  const tags = Array.isArray(fm.tags) ? (fm.tags as string[]) : [];
  const confidence = typeof fm.confidence === "string" ? fm.confidence : null;
  const updated = fm.updated != null ? String(fm.updated) : null;
  const processed = processWikiLinks(page.content);

  return (
    <div className="max-w-none">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        {tags.map((tag) => (
          <span key={tag} className="text-xs bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-full">
            {tag}
          </span>
        ))}
        {confidence && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            confidence === "high" ? "bg-green-500/20 text-green-400" :
            confidence === "medium" ? "bg-yellow-500/20 text-yellow-400" :
            "bg-red-500/20 text-red-400"
          }`}>
            {confidence}
          </span>
        )}
        {updated && (
          <span className="text-xs text-zinc-500">更新: {updated}</span>
        )}
      </div>
      <article className="prose prose-invert prose-sm max-w-none prose-headings:text-zinc-200 prose-p:text-zinc-300 prose-a:text-indigo-400 prose-strong:text-zinc-200 prose-code:text-indigo-300 prose-td:text-zinc-300 prose-th:text-zinc-200">
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
                    className="text-indigo-400 hover:text-indigo-300 underline"
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
    </div>
  );
}

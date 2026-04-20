import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { fetchWikiIndex } from "@/lib/api";
import { useWikiNavigation } from "@/hooks/useWikiNavigation";
import type { WikiIndex, WikiSection } from "@/types";

function SectionItem({ section }: { section: WikiSection }) {
  const [open, setOpen] = useState(true);
  const { currentPath, navigateTo } = useWikiNavigation();

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 w-full"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {section.title}
      </button>
      {open && (
        <div className="ml-3 mt-1.5 space-y-0.5">
          {section.items.map((item) => (
            <button
              key={item.path}
              onClick={() => navigateTo(item.path)}
              className={`flex items-center gap-2 text-sm w-full text-left px-2 py-1 rounded transition-colors ${
                currentPath === item.path
                  ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300"
                  : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:text-zinc-200 dark:hover:bg-zinc-800"
              }`}
            >
              <FileText size={13} className="shrink-0" />
              <span className="truncate">{item.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function WikiSidebar() {
  const [index, setIndex] = useState<WikiIndex | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchWikiIndex().then(setIndex).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="text-sm text-red-500 dark:text-red-400 p-2">{error}</div>;
  if (!index) return <div className="text-sm text-zinc-400 dark:text-zinc-500 p-2">加载中...</div>;

  return (
    <div className="space-y-1">
      {index.sections.map((section) => (
        <SectionItem key={section.title} section={section} />
      ))}
    </div>
  );
}

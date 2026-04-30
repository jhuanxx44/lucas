import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, FileText, FolderPlus, ArrowRight } from "lucide-react";
import { fetchWikiIndex, fetchWikiTree, wikiMkdir, wikiMove } from "@/lib/api";
import { useWikiNavigation } from "@/hooks/useWikiNavigation";
import type { WikiIndex, WikiSection, WikiTreeNode } from "@/types";

function MoveDialog({
  itemPath,
  onClose,
  onDone,
}: {
  itemPath: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [tree, setTree] = useState<WikiTreeNode[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchWikiTree().then(setTree).catch(() => setError("加载失败")).finally(() => setLoading(false));
  }, []);

  const dirs: { path: string; label: string }[] = [];
  function collectDirs(nodes: WikiTreeNode[], depth: number) {
    for (const n of nodes) {
      if (n.type === "dir") {
        dirs.push({ path: n.path, label: "  ".repeat(depth) + n.name });
        if (n.children) collectDirs(n.children, depth + 1);
      }
    }
  }
  collectDirs(tree, 0);

  const fileName = itemPath.split("/").pop() || "";

  const handleMove = async () => {
    if (!selected) return;
    try {
      await wikiMove(itemPath, `${selected}/${fileName}`);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "移动失败");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 rounded-lg shadow-xl p-4 w-72 max-h-80 flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="text-sm font-medium mb-2 text-zinc-700 dark:text-zinc-300">移动到...</div>
        {loading && <div className="text-xs text-zinc-400">加载中...</div>}
        {error && <div className="text-xs text-red-500 mb-2">{error}</div>}
        <div className="flex-1 overflow-y-auto space-y-0.5 mb-3">
          {dirs.map((d) => (
            <button
              key={d.path}
              onClick={() => setSelected(d.path)}
              className={`w-full text-left text-xs px-2 py-1 rounded whitespace-pre ${
                selected === d.path
                  ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300"
                  : "text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="text-xs px-3 py-1 rounded text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800">取消</button>
          <button onClick={handleMove} disabled={!selected} className="text-xs px-3 py-1 rounded bg-indigo-500 text-white disabled:opacity-40">移动</button>
        </div>
      </div>
    </div>
  );
}

function ItemList({
  items,
  onRefresh,
}: {
  items: WikiSection["items"];
  onRefresh: () => void;
}) {
  const { currentPath, navigateTo } = useWikiNavigation();
  const [moveTarget, setMoveTarget] = useState<string | null>(null);

  return (
    <>
      <div className="space-y-0.5">
        {items.map((item) => (
          <div key={item.path} className="flex items-center group/item">
            <button
              onClick={() => navigateTo(item.path)}
              className={`flex items-center gap-2 text-sm flex-1 text-left px-2 py-1 rounded transition-colors ${
                currentPath === item.path
                  ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-300"
                  : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:text-zinc-200 dark:hover:bg-zinc-800"
              }`}
            >
              <FileText size={13} className="shrink-0" />
              <span className="truncate">{item.name}</span>
            </button>
            <button
              onClick={() => setMoveTarget(item.path)}
              className="opacity-0 group-hover/item:opacity-100 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 p-0.5 transition-opacity shrink-0"
              title="移动"
            >
              <ArrowRight size={12} />
            </button>
          </div>
        ))}
      </div>
      {moveTarget && (
        <MoveDialog itemPath={moveTarget} onClose={() => setMoveTarget(null)} onDone={() => { setMoveTarget(null); onRefresh(); }} />
      )}
    </>
  );
}

function SubSection({
  label,
  section,
  onRefresh,
}: {
  label: string;
  section: WikiSection;
  onRefresh: () => void;
}) {
  const [open, setOpen] = useState(true);
  const [mkdirMode, setMkdirMode] = useState(false);
  const [newDirName, setNewDirName] = useState("");
  const [mkdirError, setMkdirError] = useState("");

  const sectionDir = section.items[0]?.path.split("/").slice(0, -1).join("/") || "";

  const handleMkdir = async () => {
    if (!newDirName.trim()) return;
    setMkdirError("");
    try {
      await wikiMkdir(`${sectionDir}/${newDirName.trim()}`);
      setMkdirMode(false);
      setNewDirName("");
      onRefresh();
    } catch (e) {
      setMkdirError(e instanceof Error ? e.message : "创建失败");
    }
  };

  return (
    <div>
      <div className="flex items-center group">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 text-sm text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 flex-1"
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {label}
          <span className="text-xs text-zinc-400 dark:text-zinc-500">{section.items.length}</span>
        </button>
        <button
          onClick={() => setMkdirMode(true)}
          className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 p-0.5 transition-opacity"
          title="新建子目录"
        >
          <FolderPlus size={12} />
        </button>
      </div>
      {mkdirMode && (
        <div className="ml-4 mt-1">
          <div className="flex items-center gap-1">
            <input
              autoFocus
              value={newDirName}
              onChange={(e) => setNewDirName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleMkdir(); if (e.key === "Escape") { setMkdirMode(false); setMkdirError(""); } }}
              className="text-xs border border-zinc-300 dark:border-zinc-700 rounded px-1.5 py-0.5 bg-transparent w-28 focus:outline-none focus:border-indigo-400"
              placeholder="目录名"
            />
            <button onClick={handleMkdir} className="text-xs text-indigo-500 hover:text-indigo-600">确定</button>
            <button onClick={() => { setMkdirMode(false); setMkdirError(""); }} className="text-xs text-zinc-400 hover:text-zinc-600">取消</button>
          </div>
          {mkdirError && <div className="text-xs text-red-500 mt-0.5">{mkdirError}</div>}
        </div>
      )}
      {open && (
        <div className="ml-4 mt-1">
          <ItemList items={section.items} onRefresh={onRefresh} />
        </div>
      )}
    </div>
  );
}

function SectionGroup({
  title,
  subSections,
  onRefresh,
}: {
  title: string;
  subSections: { label: string; section: WikiSection }[];
  onRefresh: () => void;
}) {
  const [open, setOpen] = useState(true);

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {title}
      </button>
      {open && (
        <div className="ml-3 mt-1.5 space-y-1">
          {subSections.map((sub) => (
            <SubSection key={sub.label} label={sub.label} section={sub.section} onRefresh={onRefresh} />
          ))}
        </div>
      )}
    </div>
  );
}

function FlatSection({ section, onRefresh }: { section: WikiSection; onRefresh: () => void }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {section.title}
      </button>
      {open && (
        <div className="ml-3 mt-1.5">
          <ItemList items={section.items} onRefresh={onRefresh} />
        </div>
      )}
    </div>
  );
}

export function WikiSidebar({ refreshKey = 0 }: { refreshKey?: number }) {
  const [index, setIndex] = useState<WikiIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localKey, setLocalKey] = useState(0);

  useEffect(() => {
    fetchWikiIndex().then(setIndex).catch((e) => setError(e.message));
  }, [refreshKey, localKey]);

  const refresh = () => setLocalKey((k) => k + 1);

  if (error) return <div className="text-sm text-red-500 dark:text-red-400 p-2">{error}</div>;
  if (!index) return <div className="text-sm text-zinc-400 dark:text-zinc-500 p-2">加载中...</div>;

  const grouped = new Map<string, { label: string; section: WikiSection }[]>();

  for (const section of index.sections) {
    const sep = section.title.indexOf(" · ");
    if (sep !== -1) {
      const parent = section.title.slice(0, sep);
      const child = section.title.slice(sep + 3);
      if (!grouped.has(parent)) grouped.set(parent, []);
      grouped.get(parent)!.push({ label: child, section });
    }
  }

  const elements: React.ReactNode[] = [];
  const rendered = new Set<string>();

  for (const section of index.sections) {
    const sep = section.title.indexOf(" · ");
    const key = sep !== -1 ? section.title.slice(0, sep) : section.title;
    if (rendered.has(key)) continue;
    rendered.add(key);

    if (grouped.has(key)) {
      elements.push(
        <SectionGroup key={key} title={key} subSections={grouped.get(key)!} onRefresh={refresh} />
      );
    } else {
      elements.push(<FlatSection key={key} section={section} onRefresh={refresh} />);
    }
  }

  return <div className="space-y-1">{elements}</div>;
}

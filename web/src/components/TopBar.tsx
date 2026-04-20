import { Search, Link2, Link2Off } from "lucide-react";

interface TopBarProps {
  linked: boolean;
  onToggleLink: () => void;
  onSearch: (query: string) => void;
}

export function TopBar({ linked, onToggleLink, onSearch }: TopBarProps) {
  return (
    <div className="h-12 border-b border-zinc-800 bg-zinc-950 flex items-center px-4 gap-4 shrink-0">
      <span className="text-lg font-bold text-indigo-400">Lucas</span>
      <span className="text-sm text-zinc-500">A股智能分析系统</span>
      <div className="ml-auto flex items-center gap-3">
        <button
          onClick={onToggleLink}
          className="text-zinc-400 hover:text-zinc-200 p-1.5 rounded-md hover:bg-zinc-800 transition-colors"
          title={linked ? "关闭联动" : "开启联动"}
        >
          {linked ? <Link2 size={16} /> : <Link2Off size={16} />}
        </button>
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="搜索 wiki 或提问..."
            className="bg-zinc-900 border border-zinc-700 rounded-md pl-8 pr-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 w-64 focus:outline-none focus:border-indigo-500"
            onKeyDown={(e) => {
              if (e.key === "Enter") onSearch((e.target as HTMLInputElement).value);
            }}
          />
        </div>
      </div>
    </div>
  );
}

import { Search, Link2, Link2Off, Menu, Sun, Moon } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";

interface TopBarProps {
  linked: boolean;
  onToggleLink: () => void;
  onSearch: (query: string) => void;
  onToggleNavigation: () => void;
}

export function TopBar({ linked, onToggleLink, onSearch, onToggleNavigation }: TopBarProps) {
  const { theme, toggle } = useTheme();

  return (
    <div className="h-12 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 flex items-center px-4 gap-4 shrink-0">
      <button
        onClick={onToggleNavigation}
        className="-ml-1 rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 md:hidden"
        title="打开导航"
      >
        <Menu size={17} />
      </button>
      <span className="text-lg font-bold text-indigo-600 dark:text-indigo-400">Lucas</span>
      <span className="hidden text-sm text-zinc-400 dark:text-zinc-500 sm:inline">投研认知的复利引擎</span>
      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={toggle}
          className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          title={theme === "dark" ? "切换亮色模式" : "切换暗色模式"}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button
          onClick={onToggleLink}
          className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          title={linked ? "关闭联动" : "开启联动"}
        >
          {linked ? <Link2 size={16} /> : <Link2Off size={16} />}
        </button>
        <div className="relative hidden md:block">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400 dark:text-zinc-500" />
          <input
            type="text"
            placeholder="搜索 wiki 或提问..."
            className="bg-zinc-100 dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md pl-8 pr-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 w-64 focus:outline-none focus:border-indigo-500"
            onKeyDown={(e) => {
              if (e.key === "Enter") onSearch((e.target as HTMLInputElement).value);
            }}
          />
        </div>
      </div>
    </div>
  );
}

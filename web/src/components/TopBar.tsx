import { Link2, Link2Off, Menu, Sun, Moon, PanelRight } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";

interface TopBarProps {
  linked: boolean;
  onToggleLink: () => void;
  onToggleNavigation: () => void;
  traceOpen: boolean;
  onToggleTrace: () => void;
}

export function TopBar({ linked, onToggleLink, onToggleNavigation, traceOpen, onToggleTrace }: TopBarProps) {
  const { theme, toggle } = useTheme();

  return (
    <div className="h-12 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/70 flex items-center px-4 gap-4 shrink-0">
      <button
        onClick={onToggleNavigation}
        className="-ml-1 rounded-md p-1.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200 md:hidden"
        title="打开导航"
      >
        <Menu size={17} />
      </button>
      <span className="text-lg font-bold text-indigo-600 dark:text-indigo-400">Lucas</span>
      <div className="ml-auto flex items-center gap-1">
        <button
          onClick={toggle}
          aria-label={theme === "dark" ? "切换亮色模式" : "切换暗色模式"}
          className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          title={theme === "dark" ? "切换亮色模式" : "切换暗色模式"}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button
          onClick={onToggleLink}
          aria-pressed={linked}
          aria-label={linked ? "关闭 Wiki 联动" : "开启 Wiki 联动"}
          className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 p-1.5 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          title={linked ? "关闭 Wiki 联动" : "开启 Wiki 联动"}
        >
          {linked ? <Link2 size={16} /> : <Link2Off size={16} />}
        </button>
        <span className="mx-1 h-4 w-px bg-zinc-200 dark:bg-zinc-700" />
        <button
          aria-pressed={traceOpen}
          aria-label={traceOpen ? "折叠右侧 Trace" : "展开右侧 Trace"}
          onClick={onToggleTrace}
          className={`p-1.5 rounded-md transition-colors ${traceOpen ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-400" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"}`}
          title={traceOpen ? "折叠右侧 Trace" : "展开右侧 Trace"}
        >
          <PanelRight size={16} />
        </button>
      </div>
    </div>
  );
}

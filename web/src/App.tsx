import { useState, useCallback } from "react";
import { TopBar } from "@/components/TopBar";
import { ResizableDivider } from "@/components/ResizableDivider";
import { WikiSidebar } from "@/components/WikiSidebar";
import { WikiContent } from "@/components/WikiContent";
import { ChatPanel } from "@/components/ChatPanel";
import { WikiNavigationContext } from "@/hooks/useWikiNavigation";
import { ThemeContext, useThemeProvider } from "@/hooks/useTheme";
import { fetchWikiIndex, searchWiki } from "@/lib/api";

export default function App() {
  const themeCtx = useThemeProvider();
  const [linked, setLinked] = useState(true);
  const [leftWidth, setLeftWidth] = useState(240);
  const [rightWidth, setRightWidth] = useState(400);
  const [currentPath, setCurrentPath] = useState<string | null>(null);

  const handleLeftResize = useCallback((delta: number) => {
    setLeftWidth((w) => Math.max(180, Math.min(400, w + delta)));
  }, []);

  const handleRightResize = useCallback((delta: number) => {
    const maxW = Math.floor(window.innerWidth / 2);
    setRightWidth((w) => Math.max(300, Math.min(maxW, w - delta)));
  }, []);

  const navigateTo = useCallback((path: string) => {
    setCurrentPath(path);
  }, []);

  const handleResearchTarget = useCallback(
    (target: string) => {
      if (!linked) return;
      fetchWikiIndex().then((idx) => {
        for (const section of idx.sections) {
          for (const item of section.items) {
            if (item.name.includes(target) || target.includes(item.name)) {
              setCurrentPath(item.path);
              return;
            }
          }
        }
      });
    },
    [linked]
  );

  const handleSearch = useCallback(async (query: string) => {
    const results = await searchWiki(query);
    if (results.length > 0) {
      setCurrentPath(results[0].path);
    }
  }, []);

  return (
    <ThemeContext.Provider value={themeCtx}>
      <WikiNavigationContext.Provider value={{ currentPath, navigateTo, linked }}>
        <div className="h-screen flex flex-col bg-white text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
          <TopBar
            linked={linked}
            onToggleLink={() => setLinked((v) => !v)}
            onSearch={handleSearch}
          />
          <div className="flex flex-1 overflow-hidden">
            <div style={{ width: leftWidth }} className="shrink-0 overflow-y-auto border-r border-zinc-200 dark:border-zinc-800 p-3">
              <WikiSidebar />
            </div>
            <ResizableDivider onResize={handleLeftResize} />
            <div className="flex-1 overflow-y-auto p-4">
              <WikiContent />
            </div>
            <ResizableDivider onResize={handleRightResize} />
            <div style={{ width: rightWidth }} className="shrink-0 overflow-hidden flex flex-col border-l border-zinc-200 dark:border-zinc-800">
              <ChatPanel onResearchTarget={handleResearchTarget} />
            </div>
          </div>
        </div>
      </WikiNavigationContext.Provider>
    </ThemeContext.Provider>
  );
}

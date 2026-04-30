import { useState, useCallback } from "react";
import { TopBar } from "@/components/TopBar";
import { ResizableDivider } from "@/components/ResizableDivider";
import { WikiSidebar } from "@/components/WikiSidebar";
import { RawSidebar } from "@/components/RawSidebar";
import { WikiContent } from "@/components/WikiContent";
import { ChatPanel } from "@/components/ChatPanel";
import { WikiNavigationContext } from "@/hooks/useWikiNavigation";
import { ThemeContext, useThemeProvider } from "@/hooks/useTheme";
import { fetchWikiIndex, searchWiki, rawPdfUrl } from "@/lib/api";

export default function App() {
  const themeCtx = useThemeProvider();
  const [linked, setLinked] = useState(true);
  const [leftWidth, setLeftWidth] = useState(240);
  const [rightWidth, setRightWidth] = useState(520);
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [sidebarKey, setSidebarKey] = useState(0);
  const [sidebarTab, setSidebarTab] = useState<"wiki" | "raw">("wiki");

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

  const handleResearchDone = useCallback(() => {
    setSidebarKey((k) => k + 1);
  }, []);

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
            <div style={{ width: leftWidth }} className="shrink-0 overflow-y-auto border-r border-zinc-200 dark:border-zinc-800 flex flex-col">
              <div className="flex border-b border-zinc-200 dark:border-zinc-800 shrink-0">
                <button
                  onClick={() => setSidebarTab("wiki")}
                  className={`flex-1 text-xs py-2 font-medium transition-colors ${sidebarTab === "wiki" ? "text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-500" : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"}`}
                >
                  Wiki
                </button>
                <button
                  onClick={() => setSidebarTab("raw")}
                  className={`flex-1 text-xs py-2 font-medium transition-colors ${sidebarTab === "raw" ? "text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-500" : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"}`}
                >
                  原始资料
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-3">
                {sidebarTab === "wiki" ? <WikiSidebar refreshKey={sidebarKey} /> : <RawSidebar />}
              </div>
            </div>
            <ResizableDivider onResize={handleLeftResize} />
            {currentPath && (
              <>
                <div className="flex-1 overflow-y-auto p-4">
                  {currentPath.startsWith("__raw_pdf__/") ? (
                    <iframe
                      src={rawPdfUrl(currentPath.replace("__raw_pdf__/", ""))}
                      className="w-full h-full rounded border border-zinc-200 dark:border-zinc-700"
                      title="PDF Preview"
                    />
                  ) : (
                    <WikiContent />
                  )}
                </div>
                <ResizableDivider onResize={handleRightResize} />
              </>
            )}
            <div style={currentPath ? { width: rightWidth } : undefined} className={`${currentPath ? 'shrink-0' : 'flex-1'} overflow-hidden flex flex-col border-l border-zinc-200 dark:border-zinc-800`}>
              <ChatPanel onResearchTarget={handleResearchTarget} onResearchDone={handleResearchDone} />
            </div>
          </div>
        </div>
      </WikiNavigationContext.Provider>
    </ThemeContext.Provider>
  );
}

import { useState, useCallback, useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import { TopBar } from "@/components/TopBar";
import { ResizableDivider } from "@/components/ResizableDivider";
import { WikiSidebar } from "@/components/WikiSidebar";
import { SessionSidebar } from "@/components/SessionSidebar";
import { WikiContent } from "@/components/WikiContent";
import { ChatPanel } from "@/components/ChatPanel";
import { WikiNavigationContext } from "@/hooks/useWikiNavigation";
import { ThemeContext, useThemeProvider } from "@/hooks/useTheme";
import {
  createSession,
  deleteSession,
  fetchSession,
  fetchSessions,
  fetchWikiIndex,
  renameSession,
  replaceSessionMessages,
  searchWiki,
} from "@/lib/api";
import type { ChatMessage, ChatSession, ChatSessionSummary } from "@/types";

function toSummary(session: ChatSession): ChatSessionSummary {
  return {
    id: session.id,
    title: session.title,
    created_at: session.created_at,
    updated_at: session.updated_at,
    message_count: session.messages.length,
  };
}

async function loadInitialSession() {
  const existing = await fetchSessions();
  if (existing.length > 0) {
    return { sessions: existing, active: await fetchSession(existing[0].id) };
  }
  const active = await createSession();
  return { sessions: [toSummary(active)], active };
}

export default function App() {
  const themeCtx = useThemeProvider();
  const [linked, setLinked] = useState(true);
  const [leftWidth, setLeftWidth] = useState(240);
  const [rightWidth, setRightWidth] = useState(520);
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [sidebarKey, setSidebarKey] = useState(0);
  const [sidebarTab, setSidebarTab] = useState<"sessions" | "wiki">("sessions");
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const initialSessionPromise = useRef<ReturnType<typeof loadInitialSession> | null>(null);

  useEffect(() => {
    let cancelled = false;
    initialSessionPromise.current ??= loadInitialSession();
    initialSessionPromise.current
      .then(({ sessions: loadedSessions, active }) => {
        if (cancelled) return;
        setSessions(loadedSessions);
        setActiveSession(active);
      })
      .finally(() => {
        if (!cancelled) setSessionsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

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

  const handleCreateSession = useCallback(async () => {
    const created = await createSession();
    setSessions((current) => [toSummary(created), ...current]);
    setActiveSession(created);
    setSidebarTab("sessions");
    setMobileNavigationOpen(false);
  }, []);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    if (sessionId === activeSession?.id) {
      setMobileNavigationOpen(false);
      return;
    }
    setActiveSession(await fetchSession(sessionId));
    setMobileNavigationOpen(false);
  }, [activeSession?.id]);

  const handleRenameSession = useCallback(async (sessionId: string, title: string) => {
    const updated = await renameSession(sessionId, title);
    setSessions((current) => current.map((session) => (
      session.id === sessionId ? toSummary(updated) : session
    )));
    setActiveSession((current) => current?.id === sessionId ? updated : current);
  }, []);

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    await deleteSession(sessionId);
    const remaining = sessions.filter((session) => session.id !== sessionId);
    if (remaining.length === 0) {
      const created = await createSession();
      setSessions([toSummary(created)]);
      setActiveSession(created);
      return;
    }
    setSessions(remaining);
    if (activeSession?.id === sessionId) {
      setActiveSession(await fetchSession(remaining[0].id));
    }
  }, [activeSession?.id, sessions]);

  const activeSessionId = activeSession?.id ?? null;
  const handleMessagesCommitted = useCallback(async (messages: ChatMessage[]) => {
    if (!activeSessionId) return;
    const updated = await replaceSessionMessages(activeSessionId, messages);
    setActiveSession((current) => current?.id === updated.id ? updated : current);
    setSessions((current) => [
      toSummary(updated),
      ...current.filter((session) => session.id !== updated.id),
    ]);
  }, [activeSessionId]);

  return (
    <ThemeContext.Provider value={themeCtx}>
      <WikiNavigationContext.Provider value={{ currentPath, navigateTo, linked }}>
        <div className="h-screen flex flex-col bg-white text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
          <TopBar
            linked={linked}
            onToggleLink={() => setLinked((v) => !v)}
            onSearch={handleSearch}
            onToggleNavigation={() => setMobileNavigationOpen((open) => !open)}
          />
          {mobileNavigationOpen && (
            <button
              aria-label="关闭导航"
              onClick={() => setMobileNavigationOpen(false)}
              className="fixed inset-x-0 bottom-0 top-12 z-20 bg-black/30 md:hidden"
            />
          )}
          <div className="flex flex-1 overflow-hidden">
            <div
              style={{ "--sidebar-width": `${leftWidth}px` } as CSSProperties}
              className={`${mobileNavigationOpen ? "flex" : "hidden"} fixed bottom-0 left-0 top-12 z-30 w-[min(85vw,280px)] flex-col overflow-y-auto border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 md:static md:flex md:w-[var(--sidebar-width)] md:shrink-0`}
            >
              <div className="flex border-b border-zinc-200 dark:border-zinc-800 shrink-0">
                <button
                  onClick={() => setSidebarTab("sessions")}
                  className={`flex-1 text-xs py-2 font-medium transition-colors ${sidebarTab === "sessions" ? "text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-500" : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"}`}
                >
                  对话
                </button>
                <button
                  onClick={() => setSidebarTab("wiki")}
                  className={`flex-1 text-xs py-2 font-medium transition-colors ${sidebarTab === "wiki" ? "text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-500" : "text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"}`}
                >
                  Wiki
                </button>
              </div>
              <div className={`flex-1 overflow-hidden ${sidebarTab === "wiki" ? "overflow-y-auto p-3" : "p-2"}`}>
                {sidebarTab === "wiki" ? (
                  <WikiSidebar refreshKey={sidebarKey} />
                ) : (
                  <SessionSidebar
                    sessions={sessions}
                    activeSessionId={activeSessionId}
                    onCreate={handleCreateSession}
                    onSelect={handleSelectSession}
                    onRename={handleRenameSession}
                    onDelete={handleDeleteSession}
                  />
                )}
              </div>
            </div>
            <div className="hidden md:block">
              <ResizableDivider onResize={handleLeftResize} />
            </div>
            {currentPath && (
              <>
                <div className="hidden flex-1 overflow-y-auto p-4 md:block">
                  <WikiContent />
                </div>
                <div className="hidden md:block">
                  <ResizableDivider onResize={handleRightResize} />
                </div>
              </>
            )}
            <div
              style={currentPath ? { "--chat-width": `${rightWidth}px` } as CSSProperties : undefined}
              className={`${currentPath ? "flex-1 md:w-[var(--chat-width)] md:flex-none md:shrink-0" : "flex-1"} flex flex-col overflow-hidden border-l border-zinc-200 dark:border-zinc-800`}
            >
              {activeSession ? (
                <ChatPanel
                  key={activeSession.id}
                  initialMessages={activeSession.messages}
                  onMessagesCommitted={handleMessagesCommitted}
                  onResearchTarget={handleResearchTarget}
                  onResearchDone={handleResearchDone}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-zinc-400 dark:text-zinc-500">
                  {sessionsLoading ? "加载对话…" : "无法加载对话"}
                </div>
              )}
            </div>
          </div>
        </div>
      </WikiNavigationContext.Provider>
    </ThemeContext.Provider>
  );
}

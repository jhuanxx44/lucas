import { useState } from "react";
import { Check, MessageSquare, MoreHorizontal, Pencil, Plus, Trash2, X } from "lucide-react";
import type { ChatSessionSummary } from "@/types";

interface SessionSidebarProps {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  onCreate: () => void;
  onSelect: (sessionId: string) => void;
  onRename: (sessionId: string, title: string) => void;
  onDelete: (sessionId: string) => void;
}

function groupSessions(sessions: ChatSessionSummary[]) {
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const groups = [
    { label: "今天", items: [] as ChatSessionSummary[] },
    { label: "昨天", items: [] as ChatSessionSummary[] },
    { label: "更早", items: [] as ChatSessionSummary[] },
  ];

  for (const session of sessions) {
    const date = new Date(session.updated_at);
    if (date.toDateString() === today.toDateString()) groups[0].items.push(session);
    else if (date.toDateString() === yesterday.toDateString()) groups[1].items.push(session);
    else groups[2].items.push(session);
  }
  return groups.filter((group) => group.items.length > 0);
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onCreate,
  onSelect,
  onRename,
  onDelete,
}: SessionSidebarProps) {
  const [menuId, setMenuId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const startRename = (session: ChatSessionSummary) => {
    setMenuId(null);
    setEditingId(session.id);
    setEditingTitle(session.title);
  };

  const finishRename = () => {
    if (editingId && editingTitle.trim()) onRename(editingId, editingTitle.trim());
    setEditingId(null);
  };

  return (
    <div className="flex h-full flex-col">
      <button
        onClick={onCreate}
        className="mb-3 flex w-full items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm font-medium text-zinc-700 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-600 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-500/50 dark:hover:bg-indigo-500/10 dark:hover:text-indigo-400"
      >
        <Plus size={16} />
        新对话
      </button>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-zinc-400 dark:text-zinc-500">
            暂无对话记录
          </div>
        ) : (
          groupSessions(sessions).map((group) => (
            <div key={group.label} className="mb-4">
              <div className="mb-1 px-2 text-[11px] font-medium text-zinc-400 dark:text-zinc-500">
                {group.label}
              </div>
              <div className="space-y-0.5">
                {group.items.map((session) => {
                  const selected = session.id === activeSessionId;
                  const confirmingDelete = confirmDeleteId === session.id;
                  return (
                    <div
                      key={session.id}
                      className={`group relative flex min-h-9 items-center rounded-md transition-colors ${selected ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"}`}
                    >
                      {editingId === session.id ? (
                        <div className="flex w-full items-center gap-1 px-2">
                          <input
                            autoFocus
                            aria-label="重命名对话"
                            value={editingTitle}
                            onChange={(event) => setEditingTitle(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") finishRename();
                              if (event.key === "Escape") setEditingId(null);
                            }}
                            className="min-w-0 flex-1 rounded border border-indigo-400 bg-white px-1.5 py-1 text-xs text-zinc-800 outline-none dark:bg-zinc-950 dark:text-zinc-200"
                          />
                          <button onClick={finishRename} title="保存名称" className="p-1 text-indigo-500">
                            <Check size={13} />
                          </button>
                          <button onClick={() => setEditingId(null)} title="取消重命名" className="p-1 text-zinc-400">
                            <X size={13} />
                          </button>
                        </div>
                      ) : confirmingDelete ? (
                        <div className="flex w-full items-center justify-between gap-2 px-2 text-xs">
                          <span className="text-red-500">确认删除？</span>
                          <div className="flex gap-1">
                            <button onClick={() => setConfirmDeleteId(null)} className="px-1.5 py-1 text-zinc-500">取消</button>
                            <button
                              onClick={() => {
                                setConfirmDeleteId(null);
                                onDelete(session.id);
                              }}
                              className="px-1.5 py-1 font-medium text-red-500"
                            >
                              删除
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <button
                            onClick={() => onSelect(session.id)}
                            className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left text-xs"
                            title={session.title}
                          >
                            <MessageSquare size={14} className="shrink-0 opacity-70" />
                            <span className="truncate">{session.title}</span>
                          </button>
                          <button
                            onClick={() => setMenuId(menuId === session.id ? null : session.id)}
                            title={`管理 ${session.title}`}
                            className={`mr-1 rounded p-1 transition-opacity hover:bg-zinc-200 dark:hover:bg-zinc-800 ${menuId === session.id ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}
                          >
                            <MoreHorizontal size={14} />
                          </button>
                          {menuId === session.id && (
                            <div className="absolute right-1 top-8 z-20 w-24 rounded-md border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
                              <button onClick={() => startRename(session)} className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-zinc-100 dark:hover:bg-zinc-800">
                                <Pencil size={12} /> 重命名
                              </button>
                              <button
                                onClick={() => {
                                  setMenuId(null);
                                  setConfirmDeleteId(session.id);
                                }}
                                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10"
                              >
                                <Trash2 size={12} /> 删除
                              </button>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

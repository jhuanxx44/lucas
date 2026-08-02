import { useRef, useEffect, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "./ChatInput";
import { ChatMessage, PROSE_CLASSES } from "./ChatMessage";
import { REMARK_PLUGINS } from "@/lib/markdown";
import { PlanCard } from "./PlanCard";
import { AnalysisProcess } from "./AnalysisProcess";
import type { LiveTraceTurn } from "./TracePanel";
import { fetchWikiIndex } from "@/lib/api";
import { MessageSquare, RefreshCw, TrendingUp, Building2, Lightbulb, BarChart3, Globe } from "lucide-react";
import type { ChatMessage as ChatMessageType, WikiItem } from "@/types";

interface ChatPanelProps {
  initialMessages: ChatMessageType[];
  onMessagesCommitted: (messages: ChatMessageType[]) => void;
  onResearchTarget?: (target: string) => void;
  onResearchDone?: () => void;
  onLiveTraceChange?: (turn: LiveTraceTurn | null) => void;
}

const ICONS = [TrendingUp, Building2, Lightbulb, BarChart3, Globe];

const TEMPLATES: Record<string, (name: string) => string> = {
  公司档案: (n) => `${n}最近的基本面和走势如何？`,
  行业概览: (n) => `${n}行业目前的景气度和投资机会？`,
  "概念/主题": (n) => `${n}概念有哪些核心受益标的？`,
  宏观环境: (n) => `${n}对当前市场有什么影响？`,
  分析报告: (n) => `${n}的核心结论是什么？`,
  策略方法: (n) => `${n}策略的适用场景和要点？`,
};

const FALLBACK = (n: string) => `帮我分析一下${n}`;

function pickRandom<T>(arr: T[], n: number): T[] {
  const shuffled = [...arr].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n);
}

function generateSuggestions(
  items: { item: WikiItem; section: string }[]
): { icon: typeof TrendingUp; text: string }[] {
  const picked = pickRandom(items, 3);
  return picked.map(({ item, section }, i) => {
    const template = TEMPLATES[section] || FALLBACK;
    return {
      icon: ICONS[i % ICONS.length],
      text: template(item.name),
    };
  });
}

export function ChatPanel({
  initialMessages,
  onMessagesCommitted,
  onResearchTarget,
  onResearchDone,
  onLiveTraceChange,
}: ChatPanelProps) {
  const { state, sendMessage, cancel, removeQueued } = useChat(
    initialMessages,
    onMessagesCommitted,
    onResearchTarget,
    onResearchDone,
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const isNearBottom = useRef(true);
  // 挂载时已有的消息视为历史；之后追加的才是本次会话新产生的
  const historyIds = useRef(new Set(initialMessages.map((m) => m.id)));
  const wasLoading = useRef(false);

  const [allItems, setAllItems] = useState<{ item: WikiItem; section: string }[]>([]);
  const [suggestions, setSuggestions] = useState<{ icon: typeof TrendingUp; text: string }[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchWikiIndex().then((idx) => {
      const flat = idx.sections.flatMap((s) =>
        s.items.map((item) => ({ item, section: s.title }))
      );
      setAllItems(flat);
      setSuggestions(generateSuggestions(flat));
    });
  }, []);

  const handleRefresh = useCallback(() => {
    if (allItems.length === 0) return;
    setRefreshing(true);
    setSuggestions(generateSuggestions(allItems));
    setTimeout(() => setRefreshing(false), 300);
  }, [allItems]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    isNearBottom.current = scrollHeight - scrollTop - clientHeight < 80;
  };

  useEffect(() => {
    if (scrollRef.current && isNearBottom.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [state.messages, state.researchers, state.synthesis]);

  // 发送新一轮时强制跟滚到底部：用户上翻超过阈值也不影响新轮次的观看位置
  useEffect(() => {
    if (state.isLoading && !wasLoading.current) {
      isNearBottom.current = true;
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }
    wasLoading.current = state.isLoading;
  }, [state.isLoading]);

  useEffect(() => {
    if (!onLiveTraceChange) return;
    if (!state.isLoading) {
      onLiveTraceChange(null);
      return;
    }
    const question = [...state.messages].reverse().find((message) => message.role === "user")?.content ?? "";
    onLiveTraceChange({
      question,
      answer: state.synthesis,
      steps: state.traceSteps,
      runtimeTrace: state.runtimeTrace,
      runConfig: state.runConfig ?? undefined,
    });
  }, [
    onLiveTraceChange,
    state.isLoading,
    state.messages,
    state.runConfig,
    state.runtimeTrace,
    state.synthesis,
    state.traceSteps,
  ]);

  const isEmpty = state.messages.length === 0 && !state.isLoading;

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4 mx-auto max-w-md">
            <div className="w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-500/15 flex items-center justify-center mb-4">
              <MessageSquare size={22} className="text-indigo-600 dark:text-indigo-400" />
            </div>
            <h3 className="text-base font-medium text-zinc-800 dark:text-zinc-200 mb-1">
              Lucas
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">
              投研认知的复利引擎 — Lucas 自主调研，持续编译你的专属知识库
            </p>
            <div className="w-full space-y-2">
              {suggestions.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  onClick={() => sendMessage(text)}
                  className="w-full flex items-center gap-3 text-left text-sm px-3 py-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700/60 text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-200 hover:border-indigo-300 dark:hover:border-indigo-500/40 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors"
                >
                  <Icon size={16} className="shrink-0 text-indigo-500 dark:text-indigo-400" />
                  {text}
                </button>
              ))}
            </div>
            {allItems.length > 3 && (
              <button
                onClick={handleRefresh}
                className="mt-3 flex items-center gap-1.5 text-xs text-zinc-400 dark:text-zinc-500 hover:text-indigo-500 dark:hover:text-indigo-400 transition-colors"
              >
                <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
                换一换
              </button>
            )}
          </div>
        )}

        {!isEmpty && (
          <div className="mx-auto w-full max-w-[46rem] px-4 py-4 sm:px-6">
            {state.messages.map((msg, index) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onAction={sendMessage}
                defaultOpen={
                  msg.role === "assistant"
                  && index === state.messages.length - 1
                  && !historyIds.current.has(msg.id)
                }
              />
            ))}

            {state.isLoading && <AnalysisProcess steps={state.traceSteps} live thinkingByStep={state.thinkingByStep} />}

            {/* 最终答案直播上屏：后端按 turn 缓冲确认非工具轮后才冲洗，
                此处渲染的只会是最终答案；位置与 DONE 后提交的消息正文一致 */}
            {state.isLoading && state.synthesis && (
              <div className={`streaming-answer mb-10 ${PROSE_CLASSES}`}>
                <ReactMarkdown remarkPlugins={REMARK_PLUGINS}>{state.synthesis}</ReactMarkdown>
              </div>
            )}

            {/* PlanCard 内部在全部步骤完成后自动折叠消失，避免卡片残留；state.plan 在下一轮 USER_MESSAGE 时重置 */}
            {state.plan && <PlanCard plan={state.plan} />}
          </div>
        )}
      </div>
      <ChatInput
        onSend={sendMessage}
        onCancel={cancel}
        onRemovePending={removeQueued}
        phase={state.phase}
        contextUsage={state.contextUsage}
        lastCompression={state.lastCompression}
        pendingQueue={state.pendingQueue}
      />
    </div>
  );
}

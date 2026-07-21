import { useRef, useEffect, useState, useCallback } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";
import { ResearcherCard } from "./ResearcherCard";
import { SynthesisCard } from "./SynthesisCard";
import { AnalysisProcess } from "./AnalysisProcess";
import { fetchWikiIndex } from "@/lib/api";
import { ArrowUpRight, RefreshCw, Sparkles, TrendingUp, Building2, Lightbulb, BarChart3, Globe } from "lucide-react";
import type { ChatMessage as ChatMessageType, WikiItem } from "@/types";
import type { LiveTraceTurn } from "./TracePanel";

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

export function ChatPanel({ initialMessages, onMessagesCommitted, onResearchTarget, onResearchDone, onLiveTraceChange }: ChatPanelProps) {
  const { state, sendMessage, cancel } = useChat(
    initialMessages,
    onMessagesCommitted,
    onResearchTarget,
    onResearchDone,
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const isNearBottom = useRef(true);

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

  const activeResearchers = Array.from(state.researchers.values());
  const isEmpty = state.messages.length === 0 && !state.isLoading;

  useEffect(() => {
    onLiveTraceChange?.(
      state.isLoading && state.activeQuestion
        ? { question: state.activeQuestion, steps: state.traceSteps }
        : null
    );
  }, [onLiveTraceChange, state.activeQuestion, state.isLoading, state.traceSteps]);

  return (
    <div className="relative flex h-full min-w-0 flex-col bg-white dark:bg-zinc-950">
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        {isEmpty && (
          <div className="mx-auto flex h-full w-full max-w-4xl flex-col justify-center px-5 pb-24 sm:px-8">
            <div className="mb-5 text-indigo-600 dark:text-indigo-400">
              <Sparkles size={22} strokeWidth={1.8} />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100 sm:text-3xl">
              今天想研究什么？
            </h1>
            <p className="mb-8 mt-2 max-w-lg text-sm leading-6 text-zinc-500 dark:text-zinc-400">
              从公司基本面、行业趋势或已有 Wiki 开始，Lucas 会整理资料并给出可追溯的分析。
            </p>
            <div className="grid gap-2 lg:grid-cols-3">
              {suggestions.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  onClick={() => sendMessage(text)}
                  className="group flex min-h-20 w-full items-start gap-3 rounded-xl border border-zinc-200 p-3.5 text-left text-sm text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-50 active:scale-[0.99] dark:border-zinc-800 dark:text-zinc-400 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
                >
                  <Icon size={16} className="mt-0.5 shrink-0 text-indigo-500 dark:text-indigo-400" />
                  <span className="leading-5">{text}</span>
                  <ArrowUpRight size={14} className="ml-auto shrink-0 text-zinc-300 transition-colors group-hover:text-zinc-500 dark:text-zinc-700 dark:group-hover:text-zinc-400" />
                </button>
              ))}
            </div>
            {allItems.length > 3 && (
              <button
                onClick={handleRefresh}
                className="mt-3 flex w-fit items-center gap-1.5 rounded-lg px-1 py-1 text-xs text-zinc-400 transition-colors hover:text-zinc-700 dark:text-zinc-500 dark:hover:text-zinc-300"
              >
                <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
                换一换
              </button>
            )}
          </div>
        )}

        {!isEmpty && (
          <div className="mx-auto w-full max-w-3xl px-4 pb-40 pt-8 sm:px-6 sm:pt-10">
            {state.messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} onAction={sendMessage} />
            ))}

            {state.isLoading && <AnalysisProcess steps={state.traceSteps} live />}

            {state.isLoading && activeResearchers.length > 0 && (
              <div>
                {activeResearchers.filter((researcher) => researcher.text).map((researcher) => (
                  <ResearcherCard key={researcher.id} researcher={researcher} />
                ))}
                <SynthesisCard text={state.synthesis} loading={state.phase === "synthesizing"} />
              </div>
            )}
          </div>
        )}
      </div>
      <ChatInput onSend={sendMessage} onCancel={cancel} phase={state.phase} />
    </div>
  );
}

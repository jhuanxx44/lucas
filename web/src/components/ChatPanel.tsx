import { useRef, useEffect } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";
import { ResearcherCard } from "./ResearcherCard";
import { SynthesisCard } from "./SynthesisCard";
import { MessageSquare, TrendingUp, Building2, Lightbulb } from "lucide-react";

interface ChatPanelProps {
  onResearchTarget?: (target: string) => void;
}

const SUGGESTIONS = [
  { icon: TrendingUp, text: "宁德时代最近的财报表现如何？" },
  { icon: Building2, text: "AI芯片概念有哪些值得关注的公司？" },
  { icon: Lightbulb, text: "当前宏观经济环境对A股有什么影响？" },
];

export function ChatPanel({ onResearchTarget }: ChatPanelProps) {
  const { state, sendMessage } = useChat(onResearchTarget);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isNearBottom = useRef(true);

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

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-3 space-y-2">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-500/15 flex items-center justify-center mb-4">
              <MessageSquare size={22} className="text-indigo-600 dark:text-indigo-400" />
            </div>
            <h3 className="text-base font-medium text-zinc-800 dark:text-zinc-200 mb-1">
              Lucas 智能分析
            </h3>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-6">
              多研究员协作分析，为你提供全面的A股市场洞察
            </p>
            <div className="w-full space-y-2">
              {SUGGESTIONS.map(({ icon: Icon, text }) => (
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
          </div>
        )}

        {state.messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {state.isLoading && activeResearchers.length > 0 && (
          <div className="space-y-2">
            {activeResearchers.map((r) => (
              <ResearcherCard key={r.id} researcher={r} />
            ))}
            <SynthesisCard text={state.synthesis} loading={state.isLoading} />
          </div>
        )}

        {state.isLoading && activeResearchers.length === 0 && (
          <div className="text-xs text-zinc-400 dark:text-zinc-500 animate-pulse">正在分析...</div>
        )}
      </div>
      <ChatInput onSend={sendMessage} disabled={state.isLoading} />
    </div>
  );
}

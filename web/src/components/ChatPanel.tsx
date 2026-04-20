import { useRef, useEffect } from "react";
import { useChat } from "@/hooks/useChat";
import { ChatInput } from "./ChatInput";
import { ChatMessage } from "./ChatMessage";
import { ResearcherCard } from "./ResearcherCard";
import { SynthesisCard } from "./SynthesisCard";

interface ChatPanelProps {
  onResearchTarget?: (target: string) => void;
}

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

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-3 space-y-2">
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
          <div className="text-xs text-zinc-500 animate-pulse">正在分析...</div>
        )}
      </div>
      <ChatInput onSend={sendMessage} disabled={state.isLoading} />
    </div>
  );
}

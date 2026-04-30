import { useCallback } from "react";
import { userHeaders } from "@/lib/userId";

type SSEHandler = (event: string, data: unknown) => void;

interface SSEMessage {
  role: string;
  content: string;
}

export function useSSE() {
  const send = useCallback(
    async (question: string, history: SSEMessage[], onEvent: SSEHandler, signal?: AbortSignal) => {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...userHeaders() },
        body: JSON.stringify({ question, history }),
        signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Chat request failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "message";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const raw = line.slice(6);
            try {
              const data = JSON.parse(raw);
              onEvent(currentEvent, data);
            } catch {
              onEvent(currentEvent, raw);
            }
            currentEvent = "message";
          }
        }
      }
    },
    []
  );

  return { send };
}

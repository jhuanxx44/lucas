import { useEffect, useRef } from "react";
import { Braces, Brain, Check, ChevronRight, Circle, Download, Loader2, Wrench, X } from "lucide-react";
import type { ChatMessage, ChatRuntimeTraceEvent, ChatTraceStep } from "@/types";

export interface LiveTraceTurn {
  question: string;
  answer: string;
  steps: ChatTraceStep[];
  runtimeTrace: ChatRuntimeTraceEvent[];
  requestAt?: string;
  responseAt?: string;
}

interface TraceTurn {
  id: string;
  question: string;
  answer: string;
  steps: ChatTraceStep[];
  runtimeTrace: ChatRuntimeTraceEvent[];
  traceId?: string;
  traceFile?: string | null;
  requestAt?: string;
  responseAt?: string;
  live?: boolean;
}

interface TracePanelProps {
  messages: ChatMessage[];
  liveTurn: LiveTraceTurn | null;
}

function buildTurns(messages: ChatMessage[], liveTurn: LiveTraceTurn | null): TraceTurn[] {
  const turns: TraceTurn[] = [];
  let question = "";
  for (const message of messages) {
    if (message.role === "user") {
      question = message.content;
    } else {
      const rawSteps = message.traceSteps?.length
        ? message.traceSteps
        : (message.processSteps ?? []).map((label, index) => ({
            id: `${message.id}-legacy-${index}`,
            kind: "action" as const,
            label: label.startsWith("已选择研究员：")
              ? "Lucas 开始分析"
              : label === "已收到问题"
                ? "Lucas 收到问题"
                : label
                    .replace("Lucas开始", "Lucas 开始")
                    .replace("Lucas完成", "Lucas 完成")
                    .replace(/^调用 /, "Lucas 调用 "),
            status: label.includes("失败") || label.includes("取消") ? "error" as const : "done" as const,
          }));
      const steps = rawSteps.filter((step, index) => (
        index === 0 || rawSteps[index - 1].label !== step.label
      ));
      if (steps.length) turns.push({
        id: message.id,
        question,
        answer: message.content,
        steps,
        runtimeTrace: message.runtimeTrace ?? [],
        traceId: message.traceId,
        traceFile: message.traceFile,
      });
    }
  }
  if (liveTurn) {
    turns.push({ id: "live", ...liveTurn, live: true });
  }
  return turns;
}

function traceCompleteness(events: ChatRuntimeTraceEvent[], live?: boolean) {
  if (live) return "in_progress";
  const names = new Set(events.map((event) => event.event));
  const finished = events.find((event) => event.event === "run_finished");
  const finishReason = finished?.data.finishReason;
  const hasLifecycle = names.has("run_started") && names.has("run_config") && names.has("run_finished");
  const hasCompletedOutput = finishReason !== "completed" || (
    names.has("model_input")
    && names.has("model_output")
    && names.has("assistant_answer")
  );
  return hasLifecycle && hasCompletedOutput ? "complete" : "legacy_partial";
}

function exportTrace(turns: TraceTurn[], messages: ChatMessage[]) {
  // 从所有消息中提取第一个有效的 runConfig（session 级别，每次对话仅一份）
  let runConfig = undefined;
  for (const msg of messages) {
    if (msg.runConfig) {
      runConfig = msg.runConfig;
      break;
    }
  }
  const exportedAt = new Date();
  const payload: Record<string, unknown> = {
    schemaVersion: 4,
    traceType: "lucas-product-run",
    exportedAt: exportedAt.toISOString(),
    config: runConfig
      ? {
          agent: runConfig.agent,
          protocol: runConfig.protocol,
          model: runConfig.model,
          temperature: runConfig.temperature,
          allowed_tools: runConfig.allowed_tools,
          max_steps: runConfig.max_steps,
          timeout_seconds: runConfig.timeout_seconds,
          system_prompt: runConfig.system_prompt,
          tools: runConfig.tools,
          prompt_template: runConfig.prompt_template,
        }
      : undefined,
    turns: turns.map(({ live, runtimeTrace, requestAt, responseAt, ...turn }) => ({
      ...turn,
      status: live ? "running" : "finished",
      requestAt: requestAt ?? null,
      responseAt: responseAt ?? null,
      traceId: turn.traceId ?? null,
      traceFile: turn.traceFile ?? null,
      completeness: traceCompleteness(runtimeTrace, live),
      events: runtimeTrace,
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `lucas-trace-${exportedAt.toISOString().replace(/[:.]/g, "-")}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-zinc-950 p-2.5 font-mono text-[11px] leading-relaxed text-zinc-200">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function StepIcon({ step }: { step: ChatTraceStep }) {
  if (step.status === "running") return <Loader2 size={13} className="animate-spin text-indigo-500" />;
  if (step.status === "error") return <X size={13} className="text-rose-500" />;
  if (step.kind === "tool") return <Wrench size={13} className="text-amber-500" />;
  if (step.kind === "thought") return <Brain size={13} className="text-zinc-400" />;
  return <Check size={13} className="text-emerald-500" />;
}

function TraceStep({ step }: { step: ChatTraceStep }) {
  if (step.kind === "thought") {
    // 过程思考：灰色斜体，多行文本按原样展示（对齐 Codex 的 reasoning 样式）
    return (
      <div className="flex gap-2 py-1 text-xs italic leading-relaxed text-zinc-400 dark:text-zinc-500">
        <Brain size={13} className="mt-0.5 shrink-0" />
        <span className="whitespace-pre-wrap break-words">{step.label}</span>
      </div>
    );
  }

  if (step.kind !== "tool") {
    return (
      <div className="flex items-center gap-2 py-1.5 text-xs text-zinc-600 dark:text-zinc-400">
        <StepIcon step={step} />
        <span>{step.label}</span>
      </div>
    );
  }

  return (
    <details className="group rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-2 text-xs text-zinc-700 dark:text-zinc-300">
        <ChevronRight size={12} className="shrink-0 transition-transform group-open:rotate-90" />
        <StepIcon step={step} />
        <span className="truncate font-mono">{step.tool}</span>
        {step.step !== undefined && <span className="ml-auto text-[10px] text-zinc-400">STEP {step.step}</span>}
      </summary>
      <div className="space-y-3 border-t border-zinc-100 px-2.5 py-2.5 dark:border-zinc-800">
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-zinc-400">
            <Braces size={11} /> 输入
          </div>
          <JsonBlock value={step.input ?? {}} />
        </div>
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-zinc-400">
            <Circle size={8} /> 输出
          </div>
          <JsonBlock value={step.output ?? ""} />
        </div>
      </div>
    </details>
  );
}

export function TracePanel({ messages, liveTurn }: TracePanelProps) {
  const turns = buildTurns(messages, liveTurn);
  const latestTrace = [...turns].reverse().find((turn) => turn.traceId);

  const scrollRef = useRef<HTMLDivElement>(null);
  // 是否处于「贴底跟随」状态；用户手动上滚离开底部时置 false，滚回底部再恢复。
  const stickToBottomRef = useRef(true);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    // 距底 <=24px 视为贴底，容忍亚像素与惯性滚动的抖动。
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom <= 24;
  };

  // trace 内容变化时自动滚到底，但仅在用户没有主动上滑（仍贴底）时才滚，避免抢占滚动。
  // 依赖内容长度指纹：新增步骤、live 步骤增长都会触发。
  const contentFingerprint = turns.reduce((sum, turn) => sum + turn.steps.length, turns.length);
  useEffect(() => {
    if (!stickToBottomRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [contentFingerprint]);

  return (
    <aside className="flex h-full w-full flex-col bg-zinc-50 dark:bg-zinc-900/70">
      <div className="flex h-11 shrink-0 items-center border-b border-zinc-200 px-3 dark:border-zinc-800">
        <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Trace</span>
        <span className="ml-2 rounded-full bg-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
          {turns.length} 轮
        </span>
        {latestTrace?.traceId && (
          <span
            title={latestTrace.traceFile ?? latestTrace.traceId}
            className="ml-1 max-w-[10rem] truncate rounded bg-zinc-200 px-1.5 py-0.5 font-mono text-[9px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
          >
            {latestTrace.traceId}
          </span>
        )}
        <button
          aria-label="导出 Trace JSON"
          title="导出 Trace JSON"
          disabled={turns.length === 0}
          onClick={() => exportTrace(turns, messages)}
          className="ml-auto rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-200 hover:text-zinc-700 disabled:pointer-events-none disabled:opacity-30 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        >
          <Download size={15} />
        </button>
      </div>
      <div ref={scrollRef} onScroll={handleScroll} className="flex-1 space-y-3 overflow-y-auto p-3">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-xs text-zinc-400 dark:text-zinc-500">
            <Wrench size={20} className="mb-2 opacity-60" />
            发起一次对话后，这里会显示 Lucas 的动作和工具调用。
          </div>
        ) : turns.map((turn, index) => (
          <section key={turn.id} className="rounded-xl border border-zinc-200 bg-zinc-100/70 p-2.5 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-2 flex items-start gap-2">
              <span className="mt-0.5 shrink-0 text-[10px] font-medium text-zinc-400">#{index + 1}</span>
              <p className="line-clamp-2 text-xs font-medium leading-relaxed text-zinc-700 dark:text-zinc-300">{turn.question}</p>
              {turn.live && <span className="ml-auto shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-400">实时</span>}
            </div>
            <div className="space-y-1.5">
              {turn.steps.map((step) => <TraceStep key={step.id} step={step} />)}
            </div>
          </section>
        ))}
      </div>
    </aside>
  );
}

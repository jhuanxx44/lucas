import { ChevronRight, Loader2, Wrench } from "lucide-react";
import type { ChatTraceStep } from "@/types";

interface AnalysisProcessProps {
  steps: ChatTraceStep[];
  live?: boolean;
}

// 相邻同 label 去重（旧文案链路可能重复），思考步 label 各不相同不受影响
function dedupe(steps: ChatTraceStep[]): ChatTraceStep[] {
  return steps.filter((step, index) => index === 0 || steps[index - 1].label !== step.label);
}

function StepList({ steps, live }: AnalysisProcessProps) {
  const items = dedupe(steps);
  return (
    <ol className="ml-1.5 mt-3 space-y-2 border-l border-zinc-200 pb-1 pl-4 dark:border-zinc-800">
      {items.map((step, index) => {
        const active = live && index === items.length - 1;
        if (step.kind === "summary") {
          // 步骤摘要：醒目正文，模型每步生成的一句话旁白
          return (
            <li key={step.id} className="relative text-xs leading-5 text-zinc-600 dark:text-zinc-300">
              <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${active ? "animate-pulse bg-indigo-500" : "bg-zinc-400 dark:bg-zinc-600"}`} />
              <span className="whitespace-pre-wrap break-words">{step.label}</span>
            </li>
          );
        }
        if (step.kind === "thought") {
          // 历史会话兜底：旧的原生思考草稿，灰色斜体换行展示
          return (
            <li key={step.id} className="relative text-xs italic leading-5 text-zinc-400 dark:text-zinc-500">
              <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${active ? "animate-pulse bg-indigo-400" : "bg-zinc-300 dark:bg-zinc-700"}`} />
              <span className="whitespace-pre-wrap break-words">{step.label}</span>
            </li>
          );
        }
        if (step.kind === "tool") {
          // 工具调用：淡灰底 pill + 扳手图标，一眼可辨；失败态用琥珀色扳手
          const failed = step.status === "error";
          const running = step.status === "running";
          return (
            <li key={step.id} className="relative leading-5">
              <span className={`absolute -left-[19px] top-2 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${running || active ? "animate-pulse bg-indigo-500" : "bg-zinc-300 dark:bg-zinc-700"}`} />
              <span className="inline-flex items-center gap-1.5 rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-400">
                {running
                  ? <span className="inline-flex animate-spin"><Loader2 size={11} className="text-indigo-500" /></span>
                  : <Wrench size={11} className={failed ? "text-amber-500" : "text-zinc-400 dark:text-zinc-500"} />}
                <span className={failed ? "text-amber-600 dark:text-amber-400" : undefined}>{step.label}</span>
              </span>
            </li>
          );
        }
        return (
          <li key={step.id} className="relative text-xs leading-5 text-zinc-500 dark:text-zinc-400">
            <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${active ? "animate-pulse bg-indigo-500" : "bg-zinc-300 dark:bg-zinc-700"}`} />
            <span>{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function AnalysisProcess({ steps, live = false }: AnalysisProcessProps) {
  if (steps.length === 0) return null;
  const items = dedupe(steps);
  // “N 步”只计动作/工具，摘要/思考作为过程旁白不计入步数
  const stepCount = items.filter((s) => s.kind !== "thought" && s.kind !== "summary").length;

  if (!live) {
    return (
      <details className="group mb-5">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-200">
          <ChevronRight size={13} className="transition-transform group-open:rotate-90" />
          已分析 {stepCount} 步
        </summary>
        <StepList steps={steps} />
      </details>
    );
  }

  return (
    <details open className="group mb-6">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-300">
        <Loader2 size={13} className="animate-spin" />
        Lucas 正在分析
        <ChevronRight size={13} className="text-zinc-400 transition-transform group-open:rotate-90" />
      </summary>
      <StepList steps={steps} live />
    </details>
  );
}

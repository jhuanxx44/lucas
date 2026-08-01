import { ChevronRight, Loader2, Wrench } from "lucide-react";
import type { ChatTraceStep } from "@/types";

interface AnalysisProcessProps {
  steps: ChatTraceStep[];
  live?: boolean;
  thinkingByStep?: Record<number, string>;
  // 刚完成的轮次：时间线保持展开，避免 DONE 瞬间整条折叠造成布局猛跳；
  // 下一轮开始时由 ChatPanel 收回（不再是最后一条消息）
  defaultOpen?: boolean;
}

// 相邻同 label 去重（旧文案链路可能重复），思考步 label 各不相同不受影响
function dedupe(steps: ChatTraceStep[]): ChatTraceStep[] {
  return steps.filter((step, index) => index === 0 || steps[index - 1].label !== step.label);
}

// 当前句子：按中英文句号分句，只保留正在生成的最后一句。
// 句号刚打完、下一句还没开始时，最后一段为空，暂时保留上一句，避免空白闪烁
function currentSentence(text: string): string {
  const parts = text.split(/[。.]/);
  const last = parts.at(-1) ?? "";
  return last || (parts.at(-2) ?? "");
}

// 单行思考：固定宽度单行只展示当前句子，超出裁掉；
// 遇到句号即“刷新”——清除前面的内容，从下一句开头重新展示
function ThinkingLine({ text }: { text: string }) {
  return (
    <span className="block overflow-hidden whitespace-nowrap italic">
      {currentSentence(text)}
    </span>
  );
}

function StepList({ steps, live, thinkingByStep = {} }: AnalysisProcessProps) {
  const items = dedupe(steps);
  // 尚未提交 summary/tool 的轮次：渲染一行流式思考（live 专用）
  const committedSteps = new Set(items.flatMap((step) => (typeof step.step === "number" ? [step.step] : [])));
  const thinkingRows = live
    ? Object.entries(thinkingByStep)
        .map(([step, text]) => ({ step: Number(step), text }))
        .filter(({ step }) => !committedSteps.has(step))
        .sort((a, b) => a.step - b.step)
    : [];
  return (
    <ol className="ml-1.5 mt-3 space-y-2 border-l border-zinc-200 pb-1 pl-4 dark:border-zinc-800">
      {items.map((step, index) => {
        const active = live && index === items.length - 1;
        if (step.kind === "summary") {
          // 步骤摘要：醒目正文，模型每步生成的一句话旁白
          return (
            <li key={step.id} className="animate-step-in relative text-[13px] leading-6 text-zinc-700 dark:text-zinc-200">
              <span className={`absolute -left-[19px] top-2 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${active ? "animate-pulse bg-indigo-500" : "bg-zinc-400 dark:bg-zinc-600"}`} />
              <span className="whitespace-pre-wrap break-words">{step.label}</span>
            </li>
          );
        }
        if (step.kind === "thought") {
          // 历史会话兜底：旧的原生思考草稿，灰色斜体换行展示
          return (
            <li key={step.id} className="animate-step-in relative text-xs italic leading-5 text-zinc-400 dark:text-zinc-500">
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
            <li key={step.id} className="animate-step-in relative leading-5">
              <span className={`absolute -left-[19px] top-2 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${running || active ? "animate-pulse bg-indigo-500" : "bg-zinc-300 dark:bg-zinc-700"}`} />
              <span className="inline-flex items-center gap-1.5 rounded-md bg-zinc-100 px-2 py-0.5 font-mono text-[11px] text-zinc-500 dark:bg-zinc-800/60 dark:text-zinc-400">
                {running
                  ? <span className="inline-flex animate-spin"><Loader2 size={11} className="text-indigo-500" /></span>
                  : <Wrench size={11} className={failed ? "text-amber-500" : "text-zinc-400 dark:text-zinc-500"} />}
                <span className={failed ? "text-amber-600 dark:text-amber-400" : undefined}>{step.label}</span>
              </span>
            </li>
          );
        }
        return (
          <li key={step.id} className="animate-step-in relative text-xs leading-5 text-zinc-500 dark:text-zinc-400">
            <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${active ? "animate-pulse bg-indigo-500" : "bg-zinc-300 dark:bg-zinc-700"}`} />
            <span>{step.label}</span>
          </li>
        );
      })}
      {thinkingRows.map(({ step, text }) => (
        <li key={`thinking-${step}`} className="animate-step-in relative text-xs leading-5 text-zinc-400 dark:text-zinc-500">
          <span className="absolute -left-[19px] top-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 ring-4 ring-white dark:ring-zinc-950" />
          <ThinkingLine text={text} />
        </li>
      ))}
    </ol>
  );
}

export function AnalysisProcess({ steps, live = false, thinkingByStep, defaultOpen = false }: AnalysisProcessProps) {
  if (steps.length === 0) return null;
  const items = dedupe(steps);
  // “N 步”只计动作/工具，摘要/思考作为过程旁白不计入步数
  const stepCount = items.filter((s) => s.kind !== "thought" && s.kind !== "summary").length;

  if (!live) {
    return (
      <details className="group mb-5" open={defaultOpen || undefined}>
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-200">
          <ChevronRight size={13} className="transition-transform group-open:rotate-90" />
          已分析 {stepCount} 步
        </summary>
        <StepList steps={steps} thinkingByStep={thinkingByStep} />
      </details>
    );
  }

  return (
    <details open className="group mb-5">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-300">
        <Loader2 size={13} className="animate-spin" />
        Lucas 正在分析
        <ChevronRight size={13} className="text-zinc-400 transition-transform group-open:rotate-90" />
      </summary>
      <StepList steps={steps} live thinkingByStep={thinkingByStep} />
    </details>
  );
}

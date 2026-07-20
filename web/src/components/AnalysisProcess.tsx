import { ChevronRight, Loader2 } from "lucide-react";

interface AnalysisProcessProps {
  steps: string[];
  live?: boolean;
}

function normalizeSteps(steps: string[]): string[] {
  const normalized = steps.map((step) => {
    if (step.startsWith("已选择研究员：")) return "Lucas 开始分析";
    if (step === "已收到问题") return "Lucas 收到问题";
    if (step === "Lucas开始分析") return "Lucas 开始分析";
    if (step === "Lucas完成分析") return "Lucas 完成分析";
    return step;
  });
  return normalized.filter((step, index) => index === 0 || normalized[index - 1] !== step);
}

function ProcessSteps({ steps, live }: AnalysisProcessProps) {
  return (
    <ol className="ml-1.5 mt-3 space-y-2 border-l border-zinc-200 pb-1 pl-4 dark:border-zinc-800">
      {steps.map((step, index) => {
        const active = live && index === steps.length - 1;
        return (
          <li key={`${index}-${step}`} className="relative text-xs leading-5 text-zinc-500 dark:text-zinc-400">
            <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ring-4 ring-white dark:ring-zinc-950 ${active ? "animate-pulse bg-indigo-500" : "bg-zinc-300 dark:bg-zinc-700"}`} />
            <span>{step}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function AnalysisProcess({ steps, live = false }: AnalysisProcessProps) {
  if (steps.length === 0) return null;
  const displaySteps = normalizeSteps(steps);

  if (!live) {
    return (
      <details className="group mb-5">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-200">
          <ChevronRight size={13} className="transition-transform group-open:rotate-90" />
          已分析 {displaySteps.length} 步
        </summary>
        <ProcessSteps steps={displaySteps} />
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
      <ProcessSteps steps={displaySteps} live />
    </details>
  );
}

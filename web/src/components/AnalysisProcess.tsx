import { ChevronRight, Loader2 } from "lucide-react";

interface AnalysisProcessProps {
  steps: string[];
  live?: boolean;
}

function ProcessSteps({ steps, live }: AnalysisProcessProps) {
  return (
    <ol className="space-y-1.5 px-3 pb-3 pt-1">
      {steps.map((step, index) => {
        const active = live && index === steps.length - 1;
        return (
          <li key={`${index}-${step}`} className="flex items-start gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${active ? "animate-pulse bg-indigo-500" : "bg-zinc-300 dark:bg-zinc-700"}`} />
            <span>{step}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function AnalysisProcess({ steps, live = false }: AnalysisProcessProps) {
  if (steps.length === 0) return null;

  if (!live) {
    return (
      <details className="group mb-3 rounded-lg border border-zinc-200 bg-zinc-50/70 dark:border-zinc-800 dark:bg-zinc-900/60">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-zinc-500 dark:text-zinc-400">
          <ChevronRight size={13} className="transition-transform group-open:rotate-90" />
          分析过程
          <span className="ml-auto font-normal text-zinc-400 dark:text-zinc-600">{steps.length} 步</span>
        </summary>
        <ProcessSteps steps={steps} />
      </details>
    );
  }

  return (
    <div className="mb-3 rounded-lg border border-indigo-200/70 bg-indigo-50/50 dark:border-indigo-500/20 dark:bg-indigo-500/5">
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-indigo-600 dark:text-indigo-400">
        <Loader2 size={13} className="animate-spin" />
        分析过程
        <span className="ml-auto font-normal text-zinc-400 dark:text-zinc-600">实时更新</span>
      </div>
      <ProcessSteps steps={steps} live />
    </div>
  );
}

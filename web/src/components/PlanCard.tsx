import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { PlanState } from "@/types";

interface PlanCardProps {
  plan: PlanState;
}

const statusIcon = (status: string) => {
  switch (status) {
    case "completed":
      return <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />;
    case "in_progress":
      return <Loader2 size={16} className="animate-spin text-indigo-500 shrink-0" />;
    default:
      return <Circle size={16} className="text-zinc-300 dark:text-zinc-600 shrink-0" />;
  }
};

export function PlanCard({ plan }: PlanCardProps) {
  if (!plan.steps.length) return null;

  return (
    <div className="border border-indigo-300/40 dark:border-indigo-500/30 rounded-lg overflow-hidden mt-2">
      <div className="flex items-center gap-2 px-3 py-2 bg-indigo-50 dark:bg-indigo-500/10">
        <span>📋</span>
        <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300">执行计划</span>
      </div>
      <div className="px-3 py-2 space-y-1.5">
        {plan.steps.map((item, i) => (
          <div
            key={`${item.step}-${i}`}
            className={`flex items-center gap-2.5 text-sm transition-colors duration-500 ${
              item.status === "completed"
                ? "text-zinc-400 dark:text-zinc-500 line-through"
                : item.status === "pending"
                  ? "text-zinc-400 dark:text-zinc-500"
                  : "text-zinc-700 dark:text-zinc-300"
            }`}
          >
            {statusIcon(item.status)}
            <span>{item.step}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

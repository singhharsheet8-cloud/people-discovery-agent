"use client";

import { Search, BarChart3, HelpCircle, FileText, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "plan_searches", label: "Planning searches", icon: Search },
  { key: "execute_searches", label: "Searching sources", icon: Search },
  { key: "analyze_results", label: "Analyzing results", icon: BarChart3 },
  { key: "check_confidence", label: "Checking confidence", icon: BarChart3 },
  { key: "ask_clarification", label: "Requesting clarification", icon: HelpCircle },
  { key: "synthesize_profile", label: "Building profile", icon: FileText },
];

interface SearchProgressProps {
  currentStep: string | null;
  isActive: boolean;
}

export function SearchProgress({ currentStep, isActive }: SearchProgressProps) {
  if (!isActive && !currentStep) return null;

  const currentIdx = STEPS.findIndex((s) => s.key === currentStep);

  return (
    <div className="glass rounded-xl p-4 animate-fade-in">
      <div className="flex items-center gap-2 mb-3">
        <Loader2 className={cn("w-4 h-4 text-brand-400", isActive && "animate-spin")} />
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
          Discovery Progress
        </span>
      </div>
      <div className="space-y-2">
        {STEPS.filter((s) => s.key !== "ask_clarification" || currentStep === "ask_clarification").map((step, idx) => {
          const StepIcon = step.icon;
          const isComplete = currentIdx > idx || (!isActive && currentStep === "complete");
          const isCurrent = step.key === currentStep && isActive;

          if (idx > currentIdx + 1 && isActive) return null;

          return (
            <div key={step.key} className="flex items-center gap-3">
              <div className={cn(
                "w-6 h-6 rounded-full flex items-center justify-center shrink-0",
                isComplete && "bg-emerald-500/20 text-emerald-400",
                isCurrent && "bg-brand-500/20 text-brand-400",
                !isComplete && !isCurrent && "bg-white/5 text-gray-600",
              )}>
                {isComplete ? (
                  <CheckCircle2 size={14} />
                ) : isCurrent ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <StepIcon size={14} />
                )}
              </div>
              <span className={cn(
                "text-sm",
                isComplete && "text-gray-400",
                isCurrent && "text-white font-medium",
                !isComplete && !isCurrent && "text-gray-600",
              )}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

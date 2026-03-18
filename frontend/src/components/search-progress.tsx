"use client";

import {
  Search,
  BarChart3,
  Filter,
  Brain,
  Sparkles,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Shield,
  MessageSquare,
  Repeat2,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Maps backend current_step values → human-readable labels + icons
const STEP_CONFIG = [
  { key: "planning",          label: "Planning searches",        icon: Search,       color: "text-blue-400" },
  { key: "searching",         label: "Searching 15+ sources",    icon: Search,       color: "text-indigo-400" },
  { key: "disambiguating",    label: "Verifying identity",       icon: Shield,       color: "text-yellow-400" },
  { key: "filtering",         label: "Filtering results",        icon: Filter,       color: "text-orange-400" },
  { key: "analyzing",         label: "Analyzing sources",        icon: BarChart3,    color: "text-purple-400" },
  { key: "enriching",         label: "Enriching profile",        icon: Brain,        color: "text-pink-400" },
  { key: "iterating",         label: "Refining gaps",            icon: Repeat2,      color: "text-cyan-400" },
  { key: "refining",          label: "Targeted deep search",     icon: RefreshCw,    color: "text-teal-400" },
  { key: "scoring_sentiment", label: "Scoring reputation",       icon: MessageSquare,color: "text-rose-400" },
  { key: "synthesizing",      label: "Building profile",         icon: Sparkles,     color: "text-brand-400" },
  { key: "verifying",         label: "Verifying facts",          icon: CheckCircle2, color: "text-emerald-400" },
] as const;

// Visible steps — iterating/refining are sub-steps, collapse them into a single row
const VISIBLE_STEPS = STEP_CONFIG.filter(
  (s) => !["iterating", "refining"].includes(s.key)
);

const ALL_KEYS = STEP_CONFIG.map((s) => s.key);

function resolveStepIndex(currentStep: string | null): number {
  if (!currentStep) return -1;
  return ALL_KEYS.indexOf(currentStep as typeof ALL_KEYS[number]);
}

function visibleIndex(currentStep: string | null): number {
  if (!currentStep) return -1;
  // iterating / refining map to enriching visually
  const normalized =
    currentStep === "iterating" || currentStep === "refining"
      ? "enriching"
      : currentStep;
  return VISIBLE_STEPS.findIndex((s) => s.key === normalized);
}

interface SearchProgressProps {
  currentStep: string | null;
  isActive: boolean;
  elapsedSec?: number;
}

export function SearchProgress({ currentStep, isActive, elapsedSec }: SearchProgressProps) {
  if (!isActive && !currentStep) return null;

  const vIdx = visibleIndex(currentStep);
  const progress = isActive
    ? Math.min(100, ((vIdx + 1) / VISIBLE_STEPS.length) * 100)
    : currentStep
    ? 100
    : 0;

  const isRefineLoop =
    currentStep === "iterating" || currentStep === "refining";

  return (
    <div className="glass rounded-xl p-5 animate-fade-in space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Loader2
            className={cn(
              "w-4 h-4 text-brand-400",
              isActive && "animate-spin"
            )}
          />
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-widest">
            Discovery Pipeline
          </span>
        </div>
        <div className="flex items-center gap-3">
          {isRefineLoop && (
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-400 border border-cyan-500/20">
              Deep refinement
            </span>
          )}
          {elapsedSec !== undefined && isActive && (
            <span className="text-[11px] font-mono text-gray-500">
              {elapsedSec}s
            </span>
          )}
          {vIdx >= 0 && (
            <span className="text-[11px] font-mono text-gray-500">
              {vIdx + 1}/{VISIBLE_STEPS.length}
            </span>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-500 via-purple-500 to-emerald-500 transition-all duration-700 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Step list — only show completed, current, and next */}
      <div className="space-y-1.5">
        {VISIBLE_STEPS.map((step, idx) => {
          const StepIcon = step.icon;
          const isComplete = vIdx > idx || (!isActive && vIdx >= 0);
          const isCurrent =
            isActive &&
            (step.key === currentStep ||
              (isRefineLoop && step.key === "enriching" && idx === vIdx));

          // Only show current, done, and next one
          if (isActive && idx > vIdx + 1) return null;

          return (
            <div
              key={step.key}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-300",
                isCurrent && "bg-white/[0.06] ring-1 ring-white/10",
                isComplete && "opacity-60",
                !isCurrent && !isComplete && "opacity-30"
              )}
            >
              {isComplete ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : isCurrent ? (
                <Loader2
                  className={cn(
                    "w-4 h-4 shrink-0 animate-spin",
                    step.color
                  )}
                />
              ) : (
                <StepIcon className="w-4 h-4 text-gray-600 shrink-0" />
              )}
              <span
                className={cn(
                  "text-sm font-medium",
                  isCurrent ? "text-white" : isComplete ? "text-gray-400" : "text-gray-600"
                )}
              >
                {step.label}
              </span>
              {isCurrent && isActive && (
                <span className="ml-auto flex gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className={cn("w-1 h-1 rounded-full bg-current", step.color)}
                      style={{ animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }}
                    />
                  ))}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer hint */}
      {isActive && (
        <p className="text-[11px] text-gray-600 text-center">
          Discovery takes 60–120 seconds · AI is reading 15+ sources
        </p>
      )}
    </div>
  );
}

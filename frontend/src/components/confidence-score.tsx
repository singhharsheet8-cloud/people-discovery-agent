"use client";

import { cn, confidenceLabel, confidenceColor } from "@/lib/utils";

interface ConfidenceScoreProps {
  score: number;
  size?: "sm" | "md" | "lg";
}

export function ConfidenceScore({ score, size = "md" }: ConfidenceScoreProps) {
  const percentage = Math.round(score * 100);
  const label = confidenceLabel(score);
  const color = confidenceColor(score);

  const dimensions = {
    sm: { ring: 48, stroke: 4, text: "text-xs" },
    md: { ring: 72, stroke: 5, text: "text-sm" },
    lg: { ring: 96, stroke: 6, text: "text-base" },
  }[size];

  const radius = (dimensions.ring - dimensions.stroke * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score * circumference);

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative" style={{ width: dimensions.ring, height: dimensions.ring }}>
        <svg className="transform -rotate-90" width={dimensions.ring} height={dimensions.ring}>
          <circle
            cx={dimensions.ring / 2}
            cy={dimensions.ring / 2}
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth={dimensions.stroke}
          />
          <circle
            cx={dimensions.ring / 2}
            cy={dimensions.ring / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={dimensions.stroke}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className={cn(color, "transition-all duration-1000 ease-out")}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn("font-bold", color, dimensions.text)}>{percentage}%</span>
        </div>
      </div>
      <span className={cn("font-medium", color, size === "sm" ? "text-[10px]" : "text-xs")}>
        {label}
      </span>
    </div>
  );
}

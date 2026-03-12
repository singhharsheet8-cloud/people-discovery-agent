"use client";

import { Briefcase } from "lucide-react";

export interface TimelineEntry {
  period?: string;
  year?: string;
  role?: string;
  title?: string;
  company?: string;
  organization?: string;
  description?: string;
}

interface CareerTimelineProps {
  timeline: TimelineEntry[];
}

export default function CareerTimeline({ timeline }: CareerTimelineProps) {
  if (!timeline || timeline.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div
        className="absolute left-[11px] top-2 bottom-2 w-px bg-white/10"
        aria-hidden
      />

      <div className="space-y-0">
        {timeline.map((entry, index) => {
          const period = entry.period || entry.year || "";
          const role = entry.role || entry.title || "";
          const company = entry.company || entry.organization || "";
          const isEven = index % 2 === 0;

          return (
            <div
              key={index}
              className={`relative flex gap-4 py-4 border border-white/10 rounded-lg px-4 -mx-4 first:pt-0 ${
                isEven ? "bg-white/5" : "bg-white/[0.07]"
              }`}
            >
              {/* Dot */}
              <div
                className="relative z-10 flex-shrink-0 w-6 h-6 rounded-full bg-white/10 border-2 border-white/20 flex items-center justify-center"
                aria-hidden
              >
                <Briefcase size={12} className="text-white/70" />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0 pt-0.5">
                {(period || role || company) && (
                  <div className="space-y-1">
                    {period && (
                      <p className="text-sm font-semibold text-white">{period}</p>
                    )}
                    {(role || company) && (
                      <p className="text-sm text-gray-300">
                        {role}
                        {role && company && " · "}
                        {company}
                      </p>
                    )}
                    {entry.description && (
                      <p className="text-sm text-gray-400 mt-2 leading-relaxed">
                        {entry.description}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

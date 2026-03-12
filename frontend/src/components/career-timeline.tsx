"use client";

import { Briefcase, GraduationCap } from "lucide-react";

export interface TimelineEntry {
  period?: string;
  year?: string;
  role?: string;
  title?: string;
  company?: string;
  organization?: string;
  description?: string;
  type?: string;
  start_date?: string;
  end_date?: string;
}

interface CareerTimelineProps {
  timeline: TimelineEntry[];
}

function normalizeTitle(t: string): string {
  return t.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function normalizeCompany(c: string): string {
  return c.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function parseYear(s: string | undefined): number {
  if (!s) return 0;
  const match = s.match(/(\d{4})/);
  return match ? parseInt(match[1], 10) : 0;
}

function formatDateRange(start?: string, end?: string): string {
  if (!start && !end) return "";
  if (start && end) {
    if (end.toLowerCase() === "present") return `${start} — Present`;
    return `${start} — ${end}`;
  }
  return start || end || "";
}

function deduplicate(entries: TimelineEntry[]): TimelineEntry[] {
  const seen = new Map<string, TimelineEntry>();

  for (const entry of entries) {
    const title = entry.title || entry.role || "";
    const company = entry.company || entry.organization || "";
    const key = `${normalizeTitle(title)}::${normalizeCompany(company)}`;

    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, entry);
      continue;
    }

    const existingStart = existing.start_date || existing.period || existing.year || "";
    const newStart = entry.start_date || entry.period || entry.year || "";
    const existingHasDate = /\d{4}/.test(existingStart) && !/circa|prior/i.test(existingStart);
    const newHasDate = /\d{4}/.test(newStart) && !/circa|prior/i.test(newStart);

    if (newHasDate && !existingHasDate) {
      seen.set(key, entry);
    } else if (newHasDate && existingHasDate) {
      if ((entry.description || "").length > (existing.description || "").length) {
        seen.set(key, entry);
      }
    }
  }

  return Array.from(seen.values());
}

function sortByDate(entries: TimelineEntry[]): TimelineEntry[] {
  return entries.sort((a, b) => {
    const endA = a.end_date || a.period || a.year || "";
    const endB = b.end_date || b.period || b.year || "";

    if (/present/i.test(endA) && !/present/i.test(endB)) return -1;
    if (!/present/i.test(endA) && /present/i.test(endB)) return 1;

    const yearA = parseYear(a.start_date || a.period || a.year);
    const yearB = parseYear(b.start_date || b.period || b.year);
    if (yearA !== yearB) return yearB - yearA;

    return 0;
  });
}

export default function CareerTimeline({ timeline }: CareerTimelineProps) {
  if (!timeline || timeline.length === 0) return null;

  const deduped = deduplicate(timeline);
  const education = sortByDate(deduped.filter((e) => e.type === "education"));
  const career = sortByDate(deduped.filter((e) => e.type !== "education"));

  const renderEntry = (entry: TimelineEntry, idx: number, isEducation: boolean) => {
    const title = entry.title || entry.role || "";
    const company = entry.company || entry.organization || "";
    const dateStr = formatDateRange(
      entry.start_date || entry.period || entry.year,
      entry.end_date
    );
    const isCurrent = /present/i.test(entry.end_date || "");

    return (
      <div key={idx} className="relative flex gap-4 group">
        {/* Timeline dot + line */}
        <div className="flex flex-col items-center">
          <div
            className={`relative z-10 flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
              isCurrent
                ? "bg-blue-500/20 border-2 border-blue-500 ring-2 ring-blue-500/20"
                : isEducation
                ? "bg-purple-500/15 border-2 border-purple-500/40"
                : "bg-white/10 border-2 border-white/20"
            }`}
          >
            {isEducation ? (
              <GraduationCap size={14} className="text-purple-400" />
            ) : (
              <Briefcase size={14} className={isCurrent ? "text-blue-400" : "text-white/60"} />
            )}
          </div>
          <div className="w-px flex-1 bg-white/10 min-h-[16px]" />
        </div>

        {/* Content */}
        <div className="flex-1 pb-6 min-w-0">
          {dateStr && (
            <p className={`text-xs font-medium mb-1 ${isCurrent ? "text-blue-400" : "text-gray-500"}`}>
              {dateStr}
            </p>
          )}
          <p className={`text-sm font-semibold ${isCurrent ? "text-white" : "text-gray-200"}`}>
            {title}
          </p>
          {company && (
            <p className="text-sm text-gray-400 mt-0.5">{company}</p>
          )}
          {entry.description && (
            <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">
              {entry.description}
            </p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {career.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
            Experience
          </h3>
          <div>{career.map((e, i) => renderEntry(e, i, false))}</div>
        </div>
      )}

      {education.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
            Education
          </h3>
          <div>{education.map((e, i) => renderEntry(e, i, true))}</div>
        </div>
      )}
    </div>
  );
}

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

function extractWords(s: string): string[] {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 1);
}

function stripParens(s: string): string {
  return s.replace(/\([^)]*\)/g, "").trim();
}

function extractAbbreviation(s: string): string {
  const match = s.match(/\(([A-Z][A-Z.]+)\)/);
  return match ? match[1].replace(/\./g, "").toLowerCase() : "";
}

function companiesMatch(a: string, b: string): boolean {
  const la = a.toLowerCase().trim();
  const lb = b.toLowerCase().trim();
  if (la === lb) return true;

  const sa = stripParens(a).toLowerCase().trim();
  const sb = stripParens(b).toLowerCase().trim();
  if (sa === sb) return true;
  if (sa.includes(sb) || sb.includes(sa)) return true;

  const abbrA = extractAbbreviation(a);
  const abbrB = extractAbbreviation(b);
  if (abbrA && lb.includes(abbrA)) return true;
  if (abbrB && la.includes(abbrB)) return true;
  if (abbrA && abbrA === sb.replace(/[^a-z0-9]/g, "")) return true;
  if (abbrB && abbrB === sa.replace(/[^a-z0-9]/g, "")) return true;

  const wordsA = extractWords(stripParens(a));
  const wordsB = extractWords(stripParens(b));
  const noise = new Set(["of", "and", "the", "in", "at", "for", "institute", "university", "college"]);
  const sigA = wordsA.filter((w) => !noise.has(w));
  const sigB = wordsB.filter((w) => !noise.has(w));
  if (sigA.length > 0 && sigB.length > 0) {
    const shared = sigA.filter((w) => sigB.includes(w)).length;
    const minLen = Math.min(sigA.length, sigB.length);
    if (shared / minLen >= 0.6) return true;
  }

  return false;
}

function titlesOverlap(a: string, b: string): boolean {
  const la = a.toLowerCase().replace(/[^a-z0-9\s]/g, " ").trim();
  const lb = b.toLowerCase().replace(/[^a-z0-9\s]/g, " ").trim();
  if (la === lb) return true;
  if (la.includes(lb) || lb.includes(la)) return true;

  const wordsA = extractWords(a);
  const wordsB = extractWords(b);
  const noise = new Set(["of", "and", "the", "in", "at", "for", "a", "an", "senior", "junior"]);
  const sigA = wordsA.filter((w) => !noise.has(w));
  const sigB = wordsB.filter((w) => !noise.has(w));
  if (sigA.length === 0 || sigB.length === 0) return false;
  const shared = sigA.filter((w) => sigB.includes(w)).length;
  const minLen = Math.min(sigA.length, sigB.length);
  return shared / minLen >= 0.5;
}

function parseYear(s: string | undefined): number {
  if (!s) return 0;
  const match = s.match(/(\d{4})/);
  return match ? parseInt(match[1], 10) : 0;
}

function hasSpecificDate(s: string | undefined): boolean {
  if (!s) return false;
  return /\d{4}/.test(s) && !/circa|prior|before|after/i.test(s);
}

function formatDateRange(start?: string, end?: string): string {
  if (!start && !end) return "";
  const s = start || "";
  const e = end || "";
  if (/circa|prior|before/i.test(s) || /circa/i.test(e)) return "";
  if (s && e) {
    if (e.toLowerCase() === "present") return `${s} — Present`;
    return `${s} — ${e}`;
  }
  return s || e || "";
}

function deduplicate(entries: TimelineEntry[]): TimelineEntry[] {
  const result: TimelineEntry[] = [];

  for (const entry of entries) {
    const title = entry.title || entry.role || "";
    const company = entry.company || entry.organization || "";
    const entryType = entry.type || "role";

    let merged = false;
    for (let i = 0; i < result.length; i++) {
      const existing = result[i];
      const exTitle = existing.title || existing.role || "";
      const exCompany = existing.company || existing.organization || "";
      const exType = existing.type || "role";

      if (entryType !== exType) continue;
      if (!companiesMatch(company, exCompany)) continue;
      if (!titlesOverlap(title, exTitle)) continue;

      const exHasDate = hasSpecificDate(existing.start_date || existing.period);
      const newHasDate = hasSpecificDate(entry.start_date || entry.period);

      if (newHasDate && !exHasDate) {
        result[i] = entry;
      } else if (newHasDate && exHasDate) {
        if ((entry.title || "").length > (exTitle || "").length) {
          result[i] = { ...entry, description: entry.description || existing.description };
        }
      } else if (!newHasDate && exHasDate) {
        // keep existing — it has better dates
      } else {
        if ((entry.description || "").length > (existing.description || "").length) {
          result[i] = entry;
        }
      }
      merged = true;
      break;
    }

    if (!merged) {
      result.push(entry);
    }
  }

  return result;
}

function sortByDate(entries: TimelineEntry[]): TimelineEntry[] {
  return [...entries].sort((a, b) => {
    const endA = a.end_date || "";
    const endB = b.end_date || "";

    if (/present/i.test(endA) && !/present/i.test(endB)) return -1;
    if (!/present/i.test(endA) && /present/i.test(endB)) return 1;

    const startA = parseYear(a.start_date || a.period || a.year);
    const startB = parseYear(b.start_date || b.period || b.year);
    if (startA !== startB) return startB - startA;

    return 0;
  });
}

export default function CareerTimeline({ timeline }: CareerTimelineProps) {
  if (!timeline || timeline.length === 0) return null;

  const deduped = deduplicate(timeline);
  const education = sortByDate(deduped.filter((e) => e.type === "education"));
  const career = sortByDate(deduped.filter((e) => e.type !== "education"));

  const renderEntry = (entry: TimelineEntry, idx: number, total: number, isEducation: boolean) => {
    const title = entry.title || entry.role || "";
    const company = entry.company || entry.organization || "";
    const dateStr = formatDateRange(
      entry.start_date || entry.period || entry.year,
      entry.end_date
    );
    const isCurrent = /present/i.test(entry.end_date || "");
    const isLast = idx === total - 1;

    return (
      <div key={idx} className="relative flex gap-4">
        {/* Dot + connecting line */}
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
          {!isLast && <div className="w-px flex-1 bg-white/10 min-h-[16px]" />}
        </div>

        {/* Content */}
        <div className={`flex-1 min-w-0 ${isLast ? "pb-0" : "pb-6"}`}>
          {dateStr && (
            <p className={`text-xs font-medium mb-1 ${isCurrent ? "text-blue-400" : "text-gray-500"}`}>
              {dateStr}
            </p>
          )}
          <p className={`text-sm font-semibold ${isCurrent ? "text-white" : "text-gray-200"}`}>
            {title}
          </p>
          {company && <p className="text-sm text-gray-400 mt-0.5">{company}</p>}
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
          <div>{career.map((e, i) => renderEntry(e, i, career.length, false))}</div>
        </div>
      )}

      {education.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
            Education
          </h3>
          <div>{education.map((e, i) => renderEntry(e, i, education.length, true))}</div>
        </div>
      )}
    </div>
  );
}

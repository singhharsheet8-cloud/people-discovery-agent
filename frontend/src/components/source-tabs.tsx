"use client";

import { useState } from "react";
import {
  Linkedin,
  Twitter,
  Youtube,
  Github,
  Globe,
  Newspaper,
  MessageCircle,
  BookOpen,
  GraduationCap,
  FileJson,
  ExternalLink,
} from "lucide-react";
import type { PersonSource } from "@/lib/types";

const PLATFORM_CONFIG: Record<
  string,
  { icon: React.ElementType; label: string; color: string }
> = {
  linkedin: { icon: Linkedin, label: "LinkedIn", color: "text-blue-400" },
  twitter: { icon: Twitter, label: "Twitter", color: "text-sky-400" },
  youtube: { icon: Youtube, label: "YouTube", color: "text-red-400" },
  github: { icon: Github, label: "GitHub", color: "text-gray-300" },
  web: { icon: Globe, label: "Web/News", color: "text-emerald-400" },
  news: { icon: Newspaper, label: "Web/News", color: "text-purple-400" },
  reddit: { icon: MessageCircle, label: "Reddit", color: "text-orange-400" },
  medium: { icon: BookOpen, label: "Medium", color: "text-gray-300" },
  scholar: { icon: GraduationCap, label: "Scholar", color: "text-amber-400" },
};

function getPlatformKey(platform: string): string {
  const lower = platform.toLowerCase();
  if (["linkedin", "twitter", "youtube", "github", "reddit", "medium", "scholar"].includes(lower))
    return lower;
  if (["web", "news", "article", "blog"].includes(lower)) return "web";
  return "web";
}

function groupSourcesByPlatform(sources: PersonSource[]): Map<string, PersonSource[]> {
  const groups = new Map<string, PersonSource[]>();
  for (const s of sources) {
    const key = getPlatformKey(s.platform);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(s);
  }
  return groups;
}

interface SourceTabsProps {
  sources: PersonSource[];
}

export function SourceTabs({ sources }: SourceTabsProps) {
  const groups = groupSourcesByPlatform(sources);
  const platformOrder = [
    "linkedin",
    "twitter",
    "youtube",
    "github",
    "web",
    "reddit",
    "medium",
    "scholar",
  ];
  const tabs = platformOrder.filter((p) => groups.has(p));
  if (groups.size > 0 && !tabs.length) {
    tabs.push(...Array.from(groups.keys()));
  }
  const [activeTab, setActiveTab] = useState(tabs[0] ?? "raw");

  const activeSources = activeTab === "raw" ? [] : groups.get(activeTab) ?? [];

  if (sources.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-gray-500">
        No sources available
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] overflow-hidden">
      <div className="flex flex-wrap gap-1 p-2 border-b border-white/10 overflow-x-auto">
        {tabs.map((key) => {
          const config = PLATFORM_CONFIG[key] ?? {
            icon: Globe,
            label: key,
            color: "text-gray-400",
          };
          const Icon = config.icon;
          const count = groups.get(key)?.length ?? 0;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === key
                  ? "bg-white/10 text-white"
                  : "text-gray-400 hover:text-gray-300 hover:bg-white/5"
              }`}
            >
              <Icon size={16} className={config.color} />
              {config.label}
              <span className="text-xs text-gray-500">({count})</span>
            </button>
          );
        })}
        <button
          onClick={() => setActiveTab("raw")}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === "raw"
              ? "bg-white/10 text-white"
              : "text-gray-400 hover:text-gray-300 hover:bg-white/5"
          }`}
        >
          <FileJson size={16} />
          Raw JSON
        </button>
      </div>

      <div className="p-4 max-h-80 overflow-y-auto">
        {activeTab === "raw" ? (
          <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap break-words">
            {JSON.stringify(sources, null, 2)}
          </pre>
        ) : (
          <div className="space-y-3">
            {activeSources.map((source, idx) => (
              <a
                key={source.id || `${source.url}-${idx}`}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block p-3 rounded-lg border border-white/5 hover:border-white/10 hover:bg-white/[0.03] transition-colors group"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-gray-200 group-hover:text-white truncate flex-1">
                    {source.title || "Untitled"}
                  </p>
                  <ExternalLink
                    size={14}
                    className="text-gray-500 group-hover:text-gray-400 shrink-0"
                  />
                </div>
                <p className="text-xs text-gray-500 truncate mt-1">{source.url}</p>
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs text-gray-500">
                    Relevance: {Math.round((source.relevance_score ?? 0) * 100)}%
                  </span>
                  {source.source_reliability != null && (
                    <span className="text-xs text-gray-500">
                      Reliability: {Math.round(source.source_reliability * 100)}%
                    </span>
                  )}
                </div>
                {source.raw_content && (
                  <p className="text-xs text-gray-400 mt-2 line-clamp-3">
                    {source.raw_content.slice(0, 200)}
                    {source.raw_content.length > 200 ? "…" : ""}
                  </p>
                )}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import { Globe, Linkedin, Youtube, GraduationCap, Newspaper, Github, Twitter, Rocket, BookOpen } from "lucide-react";
import type { PersonSource } from "@/lib/types";

const PLATFORM_ICONS: Record<string, React.ElementType> = {
  linkedin: Linkedin,
  youtube: Youtube,
  github: Github,
  twitter: Twitter,
  academic: GraduationCap,
  news: Newspaper,
  crunchbase: Rocket,
  blog: BookOpen,
  web: Globe,
};

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "text-blue-400",
  youtube: "text-red-400",
  github: "text-gray-300",
  twitter: "text-sky-400",
  academic: "text-amber-400",
  news: "text-purple-400",
  crunchbase: "text-orange-400",
  blog: "text-emerald-400",
  web: "text-gray-400",
};

interface SourceCardProps {
  source: PersonSource;
}

export function SourceCard({ source }: SourceCardProps) {
  const Icon = PLATFORM_ICONS[source.platform] || Globe;
  const color = PLATFORM_COLORS[source.platform] || "text-gray-400";

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block glass glass-hover rounded-lg p-3 group"
    >
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 ${color}`}>
          <Icon size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-200 truncate group-hover:text-white transition-colors">
            {source.title}
          </p>
          <p className="text-xs text-gray-500 truncate mt-0.5">{source.url}</p>
          {source.raw_content && (
            <p className="text-xs text-gray-400 mt-1.5 line-clamp-2">{source.raw_content}</p>
          )}
        </div>
        <div className="text-xs text-gray-500 shrink-0">
          {Math.round((source.relevance_score ?? 0.5) * 100)}%
        </div>
      </div>
    </a>
  );
}

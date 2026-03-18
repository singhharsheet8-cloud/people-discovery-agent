"use client";

import { useState } from "react";
import {
  MapPin,
  Building2,
  Briefcase,
  ExternalLink,
  GraduationCap,
  Lightbulb,
  Trophy,
  Linkedin,
  Twitter,
  Github,
  Globe,
  Wrench,
  MessageCircle,
  Users,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Star,
  Zap,
} from "lucide-react";
import type { PersonProfile as ProfileType } from "@/lib/types";
import { confidenceLabel, confidenceColor } from "@/lib/utils";
import { SourceTabs } from "./source-tabs";

interface PersonProfileProps {
  profile: ProfileType;
}

const SOCIAL_ICONS: Record<string, React.ElementType> = {
  linkedin: Linkedin,
  twitter: Twitter,
  github: Github,
  x: Twitter,
  website: Globe,
  web: Globe,
};

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const colorClass = score >= 0.85 ? "bg-emerald-500" : score >= 0.6 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  );
}

function Badge({
  children,
  color = "brand",
}: {
  children: React.ReactNode;
  color?: "brand" | "purple" | "emerald" | "yellow";
}) {
  const cls = {
    brand: "bg-brand-500/15 text-brand-300 border-brand-500/20",
    purple: "bg-purple-500/15 text-purple-300 border-purple-500/20",
    emerald: "bg-emerald-500/15 text-emerald-300 border-emerald-500/20",
    yellow: "bg-yellow-500/15 text-yellow-300 border-yellow-500/20",
  }[color];
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border ${cls}`}>
      {children}
    </span>
  );
}

function Section({
  title,
  icon: Icon,
  count,
  children,
  defaultOpen = true,
}: {
  title: string;
  icon: React.ElementType;
  count?: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02] overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon size={14} className="text-gray-500" />
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</span>
          {count !== undefined && (
            <span className="text-[10px] font-mono text-gray-600 bg-white/5 px-1.5 py-0.5 rounded-full">
              {count}
            </span>
          )}
        </div>
        {open ? <ChevronUp size={14} className="text-gray-600" /> : <ChevronDown size={14} className="text-gray-600" />}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}

export function PersonProfile({ profile }: PersonProfileProps) {
  const name = profile.name || "Unknown";
  const keyFacts = profile.key_facts ?? [];
  const expertise = profile.expertise ?? [];
  const education = profile.education ?? [];
  const notableWork = profile.notable_work ?? [];
  const skills = profile.skills ?? [];
  const recommendations = profile.recommendations ?? [];
  const socialLinks = profile.social_links ?? {};
  const sources = profile.sources ?? [];

  const initials = name
    .split(" ")
    .filter(Boolean)
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "?";

  const confidencePct = Math.round((profile.confidence_score ?? 0) * 100);
  const confidenceLabelText = confidenceLabel(profile.confidence_score ?? 0);
  const confidenceColorClass = confidenceColor(profile.confidence_score ?? 0);
  const isHighConf = (profile.confidence_score ?? 0) >= 0.85;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] overflow-hidden animate-slide-up">

      {/* ── Hero Header ── */}
      <div className="relative bg-gradient-to-br from-brand-900/40 via-purple-900/20 to-transparent p-6 pb-5">
        {/* Confidence badge — top right */}
        <div className="absolute top-4 right-4 flex flex-col items-end gap-1">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-bold ${confidenceColorClass} bg-black/30 border border-white/10`}>
            {isHighConf && <CheckCircle2 size={13} />}
            {confidencePct}%
          </div>
          <span className={`text-[10px] font-medium uppercase tracking-wider ${confidenceColorClass}`}>
            {confidenceLabelText}
          </span>
        </div>

        <div className="flex items-start gap-5 pr-20">
          {/* Avatar */}
          <div className="relative shrink-0">
            {profile.image_url ? (
              <img
                src={profile.image_url}
                alt={name}
                className="w-20 h-20 rounded-2xl object-cover shadow-2xl ring-2 ring-white/15"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                  const fb = e.currentTarget.nextElementSibling as HTMLElement | null;
                  if (fb) fb.style.removeProperty("display");
                }}
              />
            ) : null}
            <div
              className="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-500 via-purple-500 to-pink-500 flex items-center justify-center text-2xl font-bold text-white shadow-2xl"
              style={{ display: profile.image_url ? "none" : "flex" }}
            >
              {initials}
            </div>
          </div>

          {/* Identity */}
          <div className="min-w-0 flex-1">
            <h2 className="text-2xl font-bold text-white tracking-tight truncate">{name}</h2>
            <div className="mt-1.5 space-y-1">
              {profile.current_role && (
                <div className="flex items-center gap-1.5 text-gray-200">
                  <Briefcase size={13} className="text-brand-400 shrink-0" />
                  <span className="text-sm font-medium">{profile.current_role}</span>
                </div>
              )}
              {profile.company && (
                <div className="flex items-center gap-1.5 text-gray-400">
                  <Building2 size={13} className="shrink-0" />
                  <span className="text-sm">{profile.company}</span>
                </div>
              )}
              {profile.location && (
                <div className="flex items-center gap-1.5 text-gray-400">
                  <MapPin size={13} className="shrink-0" />
                  <span className="text-sm">{profile.location}</span>
                </div>
              )}
            </div>

            {/* Followers + blog */}
            {(profile.followers_count || profile.blog_url) && (
              <div className="flex items-center gap-3 mt-2.5">
                {profile.followers_count ? (
                  <span className="flex items-center gap-1 text-gray-400 text-xs">
                    <Users size={11} />
                    {profile.followers_count.toLocaleString()} followers
                  </span>
                ) : null}
                {profile.blog_url ? (
                  <a
                    href={profile.blog_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-brand-400 hover:text-brand-300 text-xs transition-colors"
                  >
                    <BookOpen size={11} />
                    Blog
                    <ExternalLink size={9} />
                  </a>
                ) : null}
              </div>
            )}

            {/* Social links row */}
            {Object.keys(socialLinks).length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {Object.entries(socialLinks)
                  .filter(([, url]) => url && typeof url === "string")
                  .map(([platform, url]) => {
                    const Icon = SOCIAL_ICONS[platform.toLowerCase()] ?? Globe;
                    return (
                      <a
                        key={platform}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={platform}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-white/8 hover:bg-white/15 text-gray-300 hover:text-white border border-white/10 transition-colors"
                      >
                        <Icon size={13} />
                        {platform.charAt(0).toUpperCase() + platform.slice(1)}
                        <ExternalLink size={10} className="opacity-60" />
                      </a>
                    );
                  })}
              </div>
            )}
          </div>
        </div>

        {/* Confidence progress bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-gray-600 uppercase tracking-wider">Profile confidence</span>
            <span className="text-[10px] text-gray-600">{sources.length} sources</span>
          </div>
          <ConfidenceBar score={profile.confidence_score ?? 0} />
        </div>
      </div>

      {/* ── Body ── */}
      <div className="p-4 space-y-3">

        {/* Bio */}
        {profile.bio && (
          <div className="rounded-xl border border-white/8 bg-white/[0.02] px-4 py-3">
            <p className="text-sm text-gray-300 leading-relaxed">{profile.bio}</p>
          </div>
        )}

        {/* Expertise */}
        {expertise.length > 0 && (
          <Section title="Expertise" icon={Zap} count={expertise.length}>
            <div className="flex flex-wrap gap-2">
              {expertise.map((s, i) => (
                <Badge key={i} color="brand">{s}</Badge>
              ))}
            </div>
          </Section>
        )}

        {/* Skills */}
        {skills.length > 0 && (
          <Section title="Skills" icon={Wrench} count={skills.length} defaultOpen={false}>
            <div className="flex flex-wrap gap-2">
              {skills.map((s, i) => (
                <Badge key={i} color="purple">{s}</Badge>
              ))}
            </div>
          </Section>
        )}

        {/* Key Facts */}
        {keyFacts.length > 0 && (
          <Section title="Key Facts" icon={Lightbulb} count={keyFacts.length}>
            <ul className="space-y-2">
              {keyFacts.map((fact, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                  <Star size={12} className="text-brand-400 mt-0.5 shrink-0" />
                  {fact}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Notable Work */}
        {notableWork.length > 0 && (
          <Section title="Notable Work" icon={Trophy} count={notableWork.length} defaultOpen={false}>
            <ul className="space-y-1.5">
              {notableWork.map((w, i) => (
                <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                  <Trophy size={12} className="text-yellow-400 mt-0.5 shrink-0" />
                  {w}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Education */}
        {education.length > 0 && (
          <Section title="Education" icon={GraduationCap} count={education.length} defaultOpen={false}>
            <ul className="space-y-1.5">
              {education.map((edu, i) => (
                <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                  <GraduationCap size={12} className="text-emerald-400 mt-0.5 shrink-0" />
                  {edu}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Recommendations */}
        {recommendations.length > 0 && (
          <Section title="Recommendations" icon={MessageCircle} count={recommendations.length} defaultOpen={false}>
            <div className="space-y-3">
              {recommendations.map((rec, i) => {
                const isObj = typeof rec === "object" && rec !== null;
                const text = isObj ? (rec as { text?: string }).text : String(rec);
                const recommender = isObj
                  ? (rec as { recommender?: string; recommender_name?: string }).recommender
                    ?? (rec as { recommender_name?: string }).recommender_name
                  : undefined;
                if (!text) return null;
                return (
                  <div key={i} className="bg-white/[0.03] rounded-lg p-3 border border-white/5">
                    <p className="text-sm text-gray-300 italic leading-relaxed">
                      &ldquo;{text.length > 300 ? text.slice(0, 300) + "…" : text}&rdquo;
                    </p>
                    {recommender && (
                      <p className="text-xs text-gray-500 mt-2">— {recommender}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {/* Sources */}
        {sources.length > 0 && (
          <Section title={`Sources`} icon={CheckCircle2} count={sources.length} defaultOpen={false}>
            <SourceTabs sources={sources} />
          </Section>
        )}
      </div>
    </div>
  );
}

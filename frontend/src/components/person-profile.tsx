"use client";

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

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] overflow-hidden animate-slide-up">
      {/* Header */}
      <div className="bg-gradient-to-br from-brand-600/20 via-purple-600/10 to-transparent p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            {profile.image_url ? (
              <img
                src={profile.image_url}
                alt={name}
                className="w-16 h-16 rounded-2xl object-cover shadow-lg ring-2 ring-white/10"
                onError={(e) => {
                  // fallback to initials on broken image
                  const t = e.currentTarget;
                  t.style.display = "none";
                  const next = t.nextElementSibling as HTMLElement | null;
                  if (next) next.style.display = "flex";
                }}
              />
            ) : null}
            <div
              className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500 via-purple-500 to-pink-500 flex items-center justify-center text-xl font-bold text-white shadow-lg"
              style={{ display: profile.image_url ? "none" : "flex" }}
            >
              {initials}
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">{name}</h2>
              {profile.current_role && (
                <div className="flex items-center gap-1.5 text-gray-300 mt-1">
                  <Briefcase size={14} />
                  <span className="text-sm">{profile.current_role}</span>
                </div>
              )}
              {profile.company && (
                <div className="flex items-center gap-1.5 text-gray-400 mt-0.5">
                  <Building2 size={14} />
                  <span className="text-sm">{profile.company}</span>
                </div>
              )}
              {profile.location && (
                <div className="flex items-center gap-1.5 text-gray-400 mt-0.5">
                  <MapPin size={14} />
                  <span className="text-sm">{profile.location}</span>
                </div>
              )}
              {(profile.followers_count || profile.blog_url) && (
                <div className="flex items-center gap-3 mt-1">
                  {profile.followers_count ? (
                    <span className="flex items-center gap-1 text-gray-400 text-xs">
                      <Users size={12} />
                      {profile.followers_count.toLocaleString()} followers
                    </span>
                  ) : null}
                  {profile.blog_url ? (
                    <a
                      href={profile.blog_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-brand-400 hover:text-brand-300 text-xs"
                    >
                      <BookOpen size={12} />
                      Blog
                      <ExternalLink size={10} />
                    </a>
                  ) : null}
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <div
              className={`px-3 py-1.5 rounded-lg text-sm font-bold ${confidenceColorClass} bg-white/5`}
            >
              {confidencePct}%
            </div>
            <span className={`text-xs font-medium ${confidenceColorClass}`}>
              {confidenceLabelText}
            </span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="p-6 space-y-6">
        {/* Bio */}
        {profile.bio && (
          <div>
            <p className="text-sm text-gray-300 leading-relaxed">{profile.bio}</p>
          </div>
        )}

        {/* Key Facts */}
        {keyFacts.length > 0 && (
          <Section title="Key Facts" icon={Lightbulb}>
            <ul className="space-y-1.5">
              {keyFacts.map((fact, i) => (
                <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                  <span className="text-brand-400 mt-1 shrink-0">&#x2022;</span>
                  {fact}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Expertise */}
        {expertise.length > 0 && (
          <Section title="Expertise" icon={Trophy}>
            <div className="flex flex-wrap gap-2">
              {expertise.map((skill, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 rounded-full text-xs font-medium bg-brand-500/15 text-brand-300 border border-brand-500/20"
                >
                  {skill}
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* Skills */}
        {skills.length > 0 && (
          <Section title="Skills" icon={Wrench}>
            <div className="flex flex-wrap gap-2">
              {skills.map((skill, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/15 text-purple-300 border border-purple-500/20"
                >
                  {skill}
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* Education */}
        {education.length > 0 && (
          <Section title="Education" icon={GraduationCap}>
            <ul className="space-y-1">
              {education.map((edu, i) => (
                <li key={i} className="text-sm text-gray-300">
                  {edu}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Notable Work */}
        {notableWork.length > 0 && (
          <Section title="Notable Work" icon={Trophy}>
            <ul className="space-y-1">
              {notableWork.map((work, i) => (
                <li key={i} className="text-sm text-gray-300">
                  {work}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Recommendations */}
        {recommendations.length > 0 && (
          <Section title="Recommendations" icon={MessageCircle}>
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
                  <div
                    key={i}
                    className="bg-white/[0.03] rounded-lg p-3 border border-white/5"
                  >
                    <p className="text-sm text-gray-300 italic leading-relaxed">
                      &ldquo;{text.length > 300 ? text.slice(0, 300) + "..." : text}&rdquo;
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

        {/* Social Links */}
        {Object.keys(socialLinks).length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
              Social Links
            </h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(socialLinks)
                .filter(([, url]) => url != null && typeof url === "string" && url.length > 0)
                .map(([platform, url]) => {
                  const Icon = SOCIAL_ICONS[platform.toLowerCase()] ?? Globe;
                  return (
                    <a
                      key={platform}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white border border-white/5 transition-colors"
                    >
                      <Icon size={16} />
                      {platform}
                      <ExternalLink size={12} />
                    </a>
                  );
                })}
            </div>
          </div>
        )}

        {/* Sources */}
        {sources.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
              Sources ({sources.length})
            </h3>
            <SourceTabs sources={sources} />
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className="text-gray-500" />
        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">{title}</h3>
      </div>
      {children}
    </div>
  );
}

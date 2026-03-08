"use client";

import { MapPin, Briefcase, Building2, ExternalLink, GraduationCap, Lightbulb, Trophy } from "lucide-react";
import type { PersonProfile as ProfileType } from "@/lib/types";
import { ConfidenceScore } from "./confidence-score";
import { SourceCard } from "./source-card";

interface PersonProfileProps {
  profile: ProfileType;
}

export function PersonProfile({ profile }: PersonProfileProps) {
  const name = profile.name || "Unknown";
  const keyFacts = profile.key_facts ?? [];
  const expertise = profile.expertise ?? [];
  const education = profile.education ?? [];
  const notableWork = profile.notable_work ?? [];
  const socialLinks = profile.social_links ?? {};
  const sources = profile.sources ?? [];

  const initials = name
    .split(" ")
    .filter(Boolean)
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "?";

  return (
    <div className="glass rounded-2xl overflow-hidden animate-slide-up">
      {/* Header */}
      <div className="bg-gradient-to-r from-brand-600/20 to-purple-600/20 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-400 via-purple-500 to-pink-500 flex items-center justify-center text-xl font-bold text-white shadow-lg shadow-brand-500/20 animate-scale-in">
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
            </div>
          </div>
          <ConfidenceScore score={profile.confidence_score} size="lg" />
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

        {/* Education */}
        {education.length > 0 && (
          <Section title="Education" icon={GraduationCap}>
            <ul className="space-y-1">
              {education.map((edu, i) => (
                <li key={i} className="text-sm text-gray-300">{edu}</li>
              ))}
            </ul>
          </Section>
        )}

        {/* Notable Work */}
        {notableWork.length > 0 && (
          <Section title="Notable Work" icon={Trophy}>
            <ul className="space-y-1">
              {notableWork.map((work, i) => (
                <li key={i} className="text-sm text-gray-300">{work}</li>
              ))}
            </ul>
          </Section>
        )}

        {/* Social Links */}
        {Object.keys(socialLinks).length > 0 && (
          <div className="flex flex-wrap gap-2">
            {Object.entries(socialLinks).map(([platform, url]) => (
              <a
                key={platform}
                href={typeof url === "string" ? url : "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium glass glass-hover text-gray-300"
              >
                {platform}
                <ExternalLink size={10} />
              </a>
            ))}
          </div>
        )}

        {/* Sources */}
        {sources.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
              Sources ({sources.length})
            </h3>
            <div className="space-y-2">
              {sources.map((source, i) => (
                <SourceCard key={i} source={source} />
              ))}
            </div>
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

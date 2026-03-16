"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import {
  User,
  MapPin,
  Building,
  Briefcase,
  ExternalLink,
  Globe,
  Loader2,
  AlertTriangle,
  GraduationCap,
  Star,
  Calendar,
} from "lucide-react";
import CareerTimeline from "@/components/career-timeline";

interface PublicProfile {
  id: string;
  name: string;
  current_role?: string;
  company?: string;
  location?: string;
  bio?: string;
  image_url?: string;
  education?: Array<Record<string, string>>;
  expertise?: string[];
  notable_work?: string[];
  career_timeline?: Array<Record<string, string>>;
  social_links?: Record<string, string>;
  skills?: string[];
  recommendations?: Array<{ text?: string; recommender?: string } | string>;
  followers_count?: number;
  blog_url?: string;
  confidence_score: number;
  sources: Array<{
    platform: string;
    title: string;
    url?: string;
    confidence: number;
  }>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

export default function PublicProfilePage() {
  const params = useParams();
  const token = params.token as string;
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    fetch(`${API_BASE}/public/${token}`)
      .then((res) => {
        if (!res.ok) throw new Error(res.status === 404 ? "Profile not found or link expired" : "Failed to load profile");
        return res.json();
      })
      .then(setProfile)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <Loader2 className="animate-spin text-blue-500" size={40} />
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <div className="text-center space-y-4">
          <AlertTriangle size={48} className="text-yellow-500 mx-auto" />
          <h1 className="text-2xl font-bold text-white">Profile Unavailable</h1>
          <p className="text-gray-400">{error || "This shared link may have expired."}</p>
        </div>
      </div>
    );
  }

  const platformColors: Record<string, string> = {
    linkedin_profile: "bg-blue-500/20 text-blue-400",
    linkedin_posts: "bg-blue-500/20 text-blue-400",
    github: "bg-gray-500/20 text-gray-300",
    twitter: "bg-sky-500/20 text-sky-400",
    youtube_transcript: "bg-red-500/20 text-red-400",
    news: "bg-green-500/20 text-green-400",
    web: "bg-purple-500/20 text-purple-400",
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="rounded-2xl border border-white/10 bg-white/[0.02] overflow-hidden">
          <div className="bg-gradient-to-r from-blue-500/10 to-purple-500/10 p-8 border-b border-white/10">
            <div className="flex items-start gap-4">
              {profile.image_url ? (
                <img
                  src={profile.image_url}
                  alt={profile.name}
                  className="w-16 h-16 rounded-full object-cover ring-2 ring-white/10 shadow-lg shrink-0"
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                    const next = e.currentTarget.nextElementSibling as HTMLElement | null;
                    if (next) next.style.display = "flex";
                  }}
                />
              ) : null}
              <div
                className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-2xl font-bold text-white shrink-0"
                style={{ display: profile.image_url ? "none" : "flex" }}
              >
                {profile.name.charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <h1 className="text-3xl font-bold text-white">{profile.name}</h1>
                {(profile.current_role || profile.company) && (
                  <p className="text-lg text-gray-300 mt-1">
                    {profile.current_role}
                    {profile.current_role && profile.company && " at "}
                    {profile.company}
                  </p>
                )}
                <div className="flex flex-wrap gap-4 mt-3">
                  {profile.location && (
                    <span className="flex items-center gap-1 text-sm text-gray-400">
                      <MapPin size={14} /> {profile.location}
                    </span>
                  )}
                  <span className="flex items-center gap-1 text-sm text-gray-400">
                    <Star size={14} className="text-yellow-500" />
                    {Math.round(profile.confidence_score * 100)}% confidence
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="p-8 space-y-8">
            {profile.bio && (
              <section>
                <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <User size={18} /> About
                </h2>
                <p className="text-gray-300 leading-relaxed">{profile.bio}</p>
              </section>
            )}

            {profile.expertise && profile.expertise.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <Star size={18} /> Expertise
                </h2>
                <div className="flex flex-wrap gap-2">
                  {profile.expertise.map((skill, i) => (
                    <span key={i} className="px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-sm border border-blue-500/20">
                      {typeof skill === "string" ? skill : JSON.stringify(skill)}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {profile.education && profile.education.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <GraduationCap size={18} /> Education
                </h2>
                <div className="space-y-2">
                  {profile.education.map((edu, i) => (
                    <div key={i} className="text-gray-300">
                      {typeof edu === "string" ? edu : [edu.degree, edu.institution, edu.year].filter(Boolean).join(" — ")}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {profile.career_timeline && profile.career_timeline.length > 0 && (
              <section>
                <CareerTimeline timeline={profile.career_timeline} />
              </section>
            )}

            {profile.social_links && Object.keys(profile.social_links).length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <Globe size={18} /> Social Links
                </h2>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(profile.social_links).map(([platform, url]) =>
                    url ? (
                      <a
                        key={platform}
                        href={url.startsWith("http") ? url : `https://${url}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 text-gray-300 hover:bg-white/10 transition-colors text-sm"
                      >
                        <ExternalLink size={14} />
                        {platform}
                      </a>
                    ) : null
                  )}
                </div>
              </section>
            )}

            {profile.sources.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-white mb-3">
                  Sources ({profile.sources.length})
                </h2>
                <div className="space-y-2">
                  {profile.sources.slice(0, 15).map((s, i) => (
                    <div key={i} className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0">
                      <span className={`px-2 py-0.5 rounded text-xs ${platformColors[s.platform] || "bg-white/10 text-gray-400"}`}>
                        {s.platform}
                      </span>
                      <span className="text-gray-300 text-sm flex-1 truncate">
                        {s.title || s.url || "Untitled"}
                      </span>
                      {s.url && (
                        <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-gray-500 hover:text-white">
                          <ExternalLink size={14} />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="border-t border-white/10 p-4 text-center text-xs text-gray-600">
            Powered by People Discovery Agent
          </div>
        </div>
      </div>
    </div>
  );
}

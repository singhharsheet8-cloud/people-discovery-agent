"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import {
  Edit,
  RefreshCw,
  Trash2,
  ExternalLink,
  MapPin,
  Building2,
  Briefcase,
  Download,
  FileText,
  FileSpreadsheet,
  Loader2,
  Brain,
  TrendingUp,
  Shield,
  MessageSquare,
  GraduationCap,
  Lightbulb,
  Trophy,
  Wrench,
  MessageCircle,
  Users,
  BookOpen,
  Globe,
  Linkedin,
  Twitter,
  Github,
} from "lucide-react";
import {
  getPerson,
  deletePerson,
  reSearchPerson,
  getJob,
  exportPerson,
  getSentimentAnalysis,
  getInfluenceScore,
  getMeetingPrep,
  getFactVerification,
} from "@/lib/api";
import CareerTimeline from "@/components/career-timeline";
import type { PersonProfile, PersonSource } from "@/lib/types";
import { confidenceColor, confidenceLabel } from "@/lib/utils";

function groupSourcesByPlatform(sources: PersonSource[]): Record<string, PersonSource[]> {
  const groups: Record<string, PersonSource[]> = {};
  for (const s of sources) {
    const platform = s.platform || "web";
    const key = platform.charAt(0).toUpperCase() + platform.slice(1).replace(/_/g, " ");
    if (!groups[key]) groups[key] = [];
    groups[key].push(s);
  }
  return groups;
}

export default function PersonDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;
  const [person, setPerson] = useState<PersonProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [sourceTab, setSourceTab] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [reSearching, setReSearching] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [activeIntel, setActiveIntel] = useState<string | null>(null);
  const [intelLoading, setIntelLoading] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [intelData, setIntelData] = useState<Record<string, any>>({});

  const handleExport = async (format: "json" | "csv" | "pdf" | "pptx") => {
    setExporting(format);
    try {
      const data = await exportPerson(id, format);
      const safeName = person?.name?.replace(/\s+/g, "_") || "profile";

      if (format === "pdf" || format === "pptx") {
        const ext = format === "pptx" ? "pptx" : "pdf";
        const url = URL.createObjectURL(data as Blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${safeName}_profile.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
      } else if (format === "csv") {
        const blob = new Blob([data as string], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${safeName}_profile.csv`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${safeName}_profile.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      // ignore
    } finally {
      setExporting(null);
    }
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPerson(id)
      .then((p) => {
        if (!cancelled) {
          setPerson(p);
          const groups = groupSourcesByPlatform(p.sources || []);
          const first = Object.keys(groups)[0];
          setSourceTab(first || null);
        }
      })
      .catch(() => {
        if (!cancelled) setPerson(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleDelete = async () => {
    try {
      await deletePerson(id);
      router.push("/admin");
    } catch {
      // ignore
    } finally {
      setDeleteConfirm(false);
    }
  };

  const handleReSearch = async () => {
    setReSearching(true);
    try {
      const res = await reSearchPerson(id);
      const pollInterval = 3000;
      const maxPolls = 60;
      for (let i = 0; i < maxPolls; i++) {
        await new Promise((r) => setTimeout(r, pollInterval));
        const job = await getJob(res.job_id);
        if (job.status === "completed" || job.status === "failed") break;
      }
      const updated = await getPerson(id);
      setPerson(updated);
      const groups = groupSourcesByPlatform(updated.sources || []);
      setSourceTab(Object.keys(groups)[0] || null);
    } catch {
      // ignore
    } finally {
      setReSearching(false);
    }
  };

  if (loading || !person) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-gray-500">
        {loading ? "Loading..." : "Person not found"}
      </div>
    );
  }

  const sourceGroups = groupSourcesByPlatform(person.sources || []);
  const sourceTabs = Object.keys(sourceGroups);

  const initials = person.name
    .split(" ")
    .filter(Boolean)
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || "?";

  return (
    <div className="space-y-6">
      {/* Profile header */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            {/* Profile image or initials avatar */}
            <div className="shrink-0">
              {person.image_url ? (
                <img
                  src={person.image_url}
                  alt={person.name}
                  className="w-16 h-16 rounded-xl object-cover ring-2 ring-white/10 shadow-lg"
                  onError={(e) => {
                    e.currentTarget.style.display = "none";
                    const next = e.currentTarget.nextElementSibling as HTMLElement | null;
                    if (next) next.style.display = "flex";
                  }}
                />
              ) : null}
              <div
                className="w-16 h-16 rounded-xl bg-gradient-to-br from-brand-500 via-purple-500 to-pink-500 flex items-center justify-center text-xl font-bold text-white shadow-lg"
                style={{ display: person.image_url ? "none" : "flex" }}
              >
                {initials}
              </div>
            </div>
            <div>
            <h1 className="text-2xl font-bold text-white">{person.name}</h1>
            <div className="flex flex-wrap items-center gap-3 mt-2 text-gray-400">
              {person.current_role && (
                <span className="flex items-center gap-1">
                  <Briefcase size={14} />
                  {person.current_role}
                </span>
              )}
              {person.company && (
                <span className="flex items-center gap-1">
                  <Building2 size={14} />
                  {person.company}
                </span>
              )}
              {person.location && (
                <span className="flex items-center gap-1">
                  <MapPin size={14} />
                  {person.location}
                </span>
              )}
              {person.followers_count ? (
                <span className="flex items-center gap-1 text-xs">
                  <Users size={12} />
                  {person.followers_count.toLocaleString()} followers
                </span>
              ) : null}
              {person.blog_url ? (
                <a href={person.blog_url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-brand-400 hover:text-brand-300 text-xs">
                  <BookOpen size={12} />
                  Blog
                  <ExternalLink size={10} />
                </a>
              ) : null}
            </div>
            <span
              className={`inline-block mt-2 px-2 py-0.5 rounded text-xs font-medium ${confidenceColor(
                person.confidence_score
              )} bg-white/5`}
            >
              {Math.round(person.confidence_score * 100)}% ·{" "}
              {confidenceLabel(person.confidence_score)}
            </span>
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Link
              href={`/admin/persons/${id}/edit`}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/10 text-white hover:bg-white/15 transition-colors"
            >
              <Edit size={16} />
              Edit
            </Link>
            <div className="flex items-center rounded-lg bg-white/10 overflow-hidden">
              <button
                onClick={() => handleExport("pdf")}
                disabled={!!exporting}
                className="flex items-center gap-1 px-2.5 py-2 text-white hover:bg-white/10 transition-colors disabled:opacity-50"
                title="Export PDF"
              >
                <FileText size={14} />
                <span className="text-xs">PDF</span>
              </button>
              <button
                onClick={() => handleExport("csv")}
                disabled={!!exporting}
                className="flex items-center gap-1 px-2.5 py-2 text-white hover:bg-white/10 border-l border-white/10 transition-colors disabled:opacity-50"
                title="Export CSV"
              >
                <FileSpreadsheet size={14} />
                <span className="text-xs">CSV</span>
              </button>
              <button
                onClick={() => handleExport("pptx")}
                disabled={!!exporting}
                className="flex items-center gap-1 px-2.5 py-2 text-white hover:bg-white/10 border-l border-white/10 transition-colors disabled:opacity-50"
                title="Export PowerPoint"
              >
                <FileText size={14} />
                <span className="text-xs">PPTX</span>
              </button>
              <button
                onClick={() => handleExport("json")}
                disabled={!!exporting}
                className="flex items-center gap-1 px-2.5 py-2 text-white hover:bg-white/10 border-l border-white/10 transition-colors disabled:opacity-50"
                title="Export JSON"
              >
                <Download size={14} />
                <span className="text-xs">JSON</span>
              </button>
            </div>
            <button
              onClick={handleReSearch}
              disabled={reSearching}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/10 text-white hover:bg-white/15 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={16} className={reSearching ? "animate-spin" : ""} />
              Re-search
            </button>
            {deleteConfirm ? (
              <div className="flex gap-2">
                <button
                  onClick={handleDelete}
                  className="px-3 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30"
                >
                  Confirm
                </button>
                <button
                  onClick={() => setDeleteConfirm(false)}
                  className="px-3 py-2 rounded-lg bg-white/10 text-gray-400"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setDeleteConfirm(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 size={16} />
                Delete
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Career Timeline */}
      {Array.isArray(person.career_timeline) && person.career_timeline.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <CareerTimeline
            timeline={person.career_timeline as Array<{
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
            }>}
          />
        </div>
      )}

      {/* Bio */}
      {person.bio && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
            Bio
          </h2>
          <p className="text-gray-300 whitespace-pre-wrap">{person.bio}</p>
        </div>
      )}

      {/* Key Facts & Expertise & Skills & Education & Recommendations */}
      {(() => {
        const keyFacts = Array.isArray(person.key_facts) ? person.key_facts : [];
        const expertise = Array.isArray(person.expertise) ? person.expertise : [];
        const skills = Array.isArray(person.skills) ? person.skills : [];
        const education = Array.isArray(person.education) ? person.education : [];
        const recommendations = Array.isArray(person.recommendations) ? person.recommendations : [];
        const socialLinks = (person.social_links ?? {}) as Record<string, string>;
        const hasSections = keyFacts.length > 0 || expertise.length > 0 || skills.length > 0 || education.length > 0 || recommendations.length > 0 || Object.keys(socialLinks).length > 0;
        const SOCIAL_ICONS: Record<string, React.ElementType> = { linkedin: Linkedin, twitter: Twitter, github: Github, x: Twitter, website: Globe, web: Globe };
        if (!hasSections) return null;
        return (
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 space-y-5">
            {keyFacts.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Lightbulb size={14} className="text-gray-500" />
                  <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Key Facts</h3>
                </div>
                <ul className="space-y-1.5">
                  {keyFacts.map((fact: string, i: number) => (
                    <li key={i} className="text-sm text-gray-300 flex items-start gap-2">
                      <span className="text-brand-400 mt-1 shrink-0">&#x2022;</span>
                      {fact}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {expertise.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Trophy size={14} className="text-gray-500" />
                  <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Expertise</h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {expertise.map((item: string, i: number) => (
                    <span key={i} className="px-2.5 py-1 rounded-full text-xs font-medium bg-brand-500/15 text-brand-300 border border-brand-500/20">{item}</span>
                  ))}
                </div>
              </div>
            )}
            {skills.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Wrench size={14} className="text-gray-500" />
                  <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Skills</h3>
                </div>
                <div className="flex flex-wrap gap-2">
                  {skills.map((item: string, i: number) => (
                    <span key={i} className="px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/15 text-purple-300 border border-purple-500/20">{item}</span>
                  ))}
                </div>
              </div>
            )}
            {education.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <GraduationCap size={14} className="text-gray-500" />
                  <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Education</h3>
                </div>
                <ul className="space-y-1">
                  {education.map((edu: string, i: number) => (
                    <li key={i} className="text-sm text-gray-300">{edu}</li>
                  ))}
                </ul>
              </div>
            )}
            {recommendations.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <MessageCircle size={14} className="text-gray-500" />
                  <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Recommendations ({recommendations.length})</h3>
                </div>
                <div className="space-y-3">
                  {recommendations.map((rec: unknown, i: number) => {
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
                          &ldquo;{text.length > 300 ? text.slice(0, 300) + "..." : text}&rdquo;
                        </p>
                        {recommender && <p className="text-xs text-gray-500 mt-2">&mdash; {recommender}</p>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {Object.keys(socialLinks).length > 0 && (
              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Social Links</h3>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(socialLinks)
                    .filter(([, url]) => url != null && typeof url === "string" && url.length > 0)
                    .map(([platform, url]) => {
                      const Icon = SOCIAL_ICONS[platform.toLowerCase()] ?? Globe;
                      return (
                        <a key={platform} href={url} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white border border-white/5 transition-colors">
                          <Icon size={16} />
                          {platform}
                          <ExternalLink size={12} />
                        </a>
                      );
                    })}
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {/* Tabbed source viewer */}
      {Array.isArray(person.sources) && person.sources.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
          <div className="flex border-b border-white/10 overflow-x-auto">
            {sourceTabs.map((tab) => (
              <button
                key={tab}
                onClick={() => setSourceTab(tab)}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${
                  sourceTab === tab
                    ? "text-white border-b-2 border-blue-500 bg-white/5"
                    : "text-gray-400 hover:text-white hover:bg-white/5"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
          <div className="p-4 max-h-[400px] overflow-y-auto">
            {sourceTab && sourceGroups[sourceTab]?.map((s) => (
              <div
                key={s.id || s.url}
                className="border-b border-white/5 pb-4 mb-4 last:mb-0 last:pb-0 last:border-0"
              >
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
                >
                  {s.title || s.url}
                  <ExternalLink size={12} />
                </a>
                <p className="text-sm text-gray-500 mt-1">
                  Confidence: {Math.round((s.confidence || s.relevance_score || 0) * 100)}%
                  {s.platform && <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-white/5 text-gray-500">{s.platform}</span>}
                </p>
                {s.raw_content && (
                  <p className="text-sm text-gray-400 mt-2 line-clamp-3">
                    {s.raw_content}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Intelligence Panel */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider p-4 border-b border-white/10 flex items-center gap-2">
          <Brain size={16} className="text-purple-400" />
          AI Intelligence
        </h2>
        <div className="flex border-b border-white/10 overflow-x-auto">
          {[
            { key: "sentiment", label: "Sentiment", icon: TrendingUp },
            { key: "influence", label: "Influence Score", icon: TrendingUp },
            { key: "meeting", label: "Meeting Prep", icon: MessageSquare },
            { key: "verify", label: "Fact Verification", icon: Shield },
          ].map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={async () => {
                if (activeIntel === key) {
                  setActiveIntel(null);
                  return;
                }
                if (intelData[key]) {
                  setActiveIntel(key);
                  return;
                }
                setActiveIntel(key);
                setIntelLoading(true);
                try {
                  let result: Record<string, unknown> = {};
                  if (key === "sentiment") result = await getSentimentAnalysis(id);
                  else if (key === "influence") result = await getInfluenceScore(id);
                  else if (key === "meeting") result = await getMeetingPrep(id);
                  else if (key === "verify") result = await getFactVerification(id);
                  setIntelData((prev) => ({ ...prev, [key]: result }));
                } catch {
                  setIntelData((prev) => ({ ...prev, [key]: { error: "Analysis failed" } }));
                } finally {
                  setIntelLoading(false);
                }
              }}
              className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors flex items-center gap-2 ${
                activeIntel === key
                  ? "text-white border-b-2 border-purple-500 bg-white/5"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
        <div className="p-4">
          {!activeIntel && (
            <p className="text-gray-500 text-sm text-center py-4">Click a tab above to run AI analysis</p>
          )}
          {activeIntel && intelLoading && (
            <div className="flex items-center justify-center py-8 gap-2 text-purple-400">
              <Loader2 size={20} className="animate-spin" />
              <span>Running AI analysis...</span>
            </div>
          )}
          {activeIntel && !intelLoading && intelData[activeIntel] && (
            <IntelligenceResults type={activeIntel} data={intelData[activeIntel]} />
          )}
        </div>
      </div>

      {/* Job history */}
      {Array.isArray(person.jobs) && person.jobs.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider p-4 border-b border-white/10">
            Discovery Jobs
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Job ID
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Cost
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Latency
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Sources
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Cache
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody>
                {person.jobs.map((j) => (
                  <tr
                    key={j.id}
                    className="border-b border-white/5 hover:bg-white/5"
                  >
                    <td className="py-3 px-4 text-gray-400 font-mono text-xs">
                      {j.id.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-4 text-white">
                      ${j.total_cost?.toFixed(4) ?? "0"}
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {j.latency_ms != null
                        ? `${Math.round(j.latency_ms)}ms`
                        : "—"}
                    </td>
                    <td className="py-3 px-4 text-gray-400">{j.sources_hit}</td>
                    <td className="py-3 px-4 text-gray-400">{j.cache_hits}</td>
                    <td className="py-3 px-4 text-gray-500 text-sm">
                      {j.created_at
                        ? new Date(j.created_at).toLocaleDateString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function IntelligenceResults({ type, data }: { type: string; data: any }) {
  if (data?.error) {
    return <p className="text-red-400 text-sm">{data.error}</p>;
  }

  if (type === "sentiment") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <span className={`text-2xl font-bold ${
            data.overall_sentiment === "positive" ? "text-emerald-400" :
            data.overall_sentiment === "negative" ? "text-red-400" :
            "text-amber-400"
          }`}>
            {data.overall_sentiment?.toUpperCase()}
          </span>
          <span className="text-gray-400 text-sm">Score: {((data.sentiment_score || 0) * 100).toFixed(0)}%</span>
        </div>
        {data.public_perception && (
          <p className="text-gray-300 text-sm">{data.public_perception}</p>
        )}
        {data.strengths_in_perception?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Strengths</p>
            <div className="flex flex-wrap gap-1">
              {data.strengths_in_perception.map((s: string, i: number) => (
                <span key={i} className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-xs">{s}</span>
              ))}
            </div>
          </div>
        )}
        {data.risks?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Risks</p>
            <div className="flex flex-wrap gap-1">
              {data.risks.map((r: string, i: number) => (
                <span key={i} className="px-2 py-0.5 rounded bg-red-500/20 text-red-400 text-xs">{r}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (type === "influence") {
    const dims = data.dimensions || {};
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <span className="text-3xl font-bold text-white">{data.overall_influence_score || 0}</span>
          <span className={`px-3 py-1 rounded-full text-sm font-bold ${
            data.influence_tier === "S" ? "bg-purple-500/20 text-purple-400" :
            data.influence_tier === "A" ? "bg-blue-500/20 text-blue-400" :
            data.influence_tier === "B" ? "bg-emerald-500/20 text-emerald-400" :
            "bg-gray-500/20 text-gray-400"
          }`}>
            Tier {data.influence_tier}
          </span>
          <span className="text-sm text-gray-400">{data.growth_trajectory}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {Object.entries(dims).map(([key, val]) => {
            const d = val as { score: number; reasoning: string };
            return (
              <div key={key} className="bg-white/5 rounded-lg p-3">
                <p className="text-xs text-gray-500 capitalize">{key.replace(/_/g, " ")}</p>
                <p className="text-lg font-bold text-white">{d?.score || 0}</p>
                <p className="text-xs text-gray-400 mt-1 line-clamp-2">{d?.reasoning}</p>
              </div>
            );
          })}
        </div>
        {data.summary && <p className="text-sm text-gray-300">{data.summary}</p>}
      </div>
    );
  }

  if (type === "meeting") {
    return (
      <div className="space-y-4">
        {data.executive_summary && (
          <div className="bg-purple-500/10 rounded-lg p-4">
            <p className="text-sm text-purple-300">{data.executive_summary}</p>
          </div>
        )}
        {data.conversation_starters?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Conversation Starters</p>
            <div className="space-y-2">
              {data.conversation_starters.map((c: { topic: string; opener: string; why_relevant: string }, i: number) => (
                <div key={i} className="bg-white/5 rounded-lg p-3">
                  <p className="text-sm text-white font-medium">{c.topic}</p>
                  <p className="text-sm text-blue-300 mt-1">&ldquo;{c.opener}&rdquo;</p>
                  <p className="text-xs text-gray-500 mt-1">{c.why_relevant}</p>
                </div>
              ))}
            </div>
          </div>
        )}
        {data.topics_to_avoid?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Topics to Avoid</p>
            {data.topics_to_avoid.map((t: { topic: string; reason: string }, i: number) => (
              <div key={i} className="bg-red-500/10 rounded-lg p-3 mb-2">
                <p className="text-sm text-red-400 font-medium">{t.topic}</p>
                <p className="text-xs text-gray-400 mt-1">{t.reason}</p>
              </div>
            ))}
          </div>
        )}
        {data.their_priorities?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Their Priorities</p>
            <ul className="list-disc list-inside text-sm text-gray-300 space-y-1">
              {data.their_priorities.map((p: string, i: number) => <li key={i}>{p}</li>)}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (type === "verify") {
    return (
      <div className="space-y-4">
        <div className="flex gap-4">
          <div className="bg-white/5 rounded-lg p-3 flex-1 text-center">
            <p className="text-xs text-gray-500">Data Quality</p>
            <p className="text-2xl font-bold text-white">{((data.data_quality_score || 0) * 100).toFixed(0)}%</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3 flex-1 text-center">
            <p className="text-xs text-gray-500">Completeness</p>
            <p className="text-2xl font-bold text-white">{((data.completeness_score || 0) * 100).toFixed(0)}%</p>
          </div>
        </div>
        {data.high_confidence_facts?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Verified Facts</p>
            <ul className="space-y-1">
              {data.high_confidence_facts.map((f: string, i: number) => (
                <li key={i} className="text-sm text-emerald-400 flex items-center gap-2">
                  <Shield size={12} /> {f}
                </li>
              ))}
            </ul>
          </div>
        )}
        {data.inconsistencies?.length > 0 && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Inconsistencies Found</p>
            {data.inconsistencies.map((inc: { topic: string; source_a: string; source_b: string; resolution: string }, i: number) => (
              <div key={i} className="bg-amber-500/10 rounded-lg p-3 mb-2">
                <p className="text-sm text-amber-400 font-medium">{inc.topic}</p>
                <p className="text-xs text-gray-400 mt-1">Source A: {inc.source_a}</p>
                <p className="text-xs text-gray-400">Source B: {inc.source_b}</p>
                <p className="text-xs text-gray-300 mt-1">Resolution: {inc.resolution}</p>
              </div>
            ))}
          </div>
        )}
        {data.summary && <p className="text-sm text-gray-300">{data.summary}</p>}
      </div>
    );
  }

  return <pre className="text-xs text-gray-400 overflow-auto">{JSON.stringify(data, null, 2)}</pre>;
}

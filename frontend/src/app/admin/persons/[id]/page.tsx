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
} from "lucide-react";
import { getPerson, deletePerson, reSearchPerson, getJob, exportPerson } from "@/lib/api";
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

  const handleExport = async (format: "json" | "csv" | "pdf") => {
    setExporting(format);
    try {
      const data = await exportPerson(id, format);
      const safeName = person?.name?.replace(/\s+/g, "_") || "profile";

      if (format === "pdf") {
        const url = URL.createObjectURL(data as Blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${safeName}_profile.pdf`;
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

  return (
    <div className="space-y-6">
      {/* Profile header */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
        <div className="flex items-start justify-between gap-4">
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

      {/* Bio */}
      {person.bio && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
            Bio
          </h2>
          <p className="text-gray-300 whitespace-pre-wrap">{person.bio}</p>
        </div>
      )}

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

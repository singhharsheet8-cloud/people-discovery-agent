"use client";

import { useState, useEffect } from "react";
import {
  BarChart3,
  Users,
  Globe,
  TrendingUp,
  Building,
  Loader2,
} from "lucide-react";
import { getUsageAnalytics } from "@/lib/api";
import type { UsageAnalytics } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  completed: "#10b981",
  pending: "#f59e0b",
  failed: "#ef4444",
  in_progress: "#3b82f6",
};

export default function UsageAnalyticsPage() {
  const [data, setData] = useState<UsageAnalytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getUsageAnalytics()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-gray-500">
        <Loader2 size={32} className="animate-spin" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-red-400">
        Failed to load analytics
      </div>
    );
  }

  const discoveries = data.discoveries_last_30_days ?? [];
  const maxDiscoveries = Math.max(...discoveries.map((d) => d.count), 1);
  const sourceDist = data.source_distribution ?? [];
  const maxSource = Math.max(...sourceDist.map((s) => s.count), 1);
  const topCompanies = data.top_searched_companies ?? [];
  const statusBreakdown = data.discoveries_by_status ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <BarChart3 size={24} />
        Usage Analytics
      </h1>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <Users size={18} />
            <span className="text-sm font-medium">Total Persons</span>
          </div>
          <p className="text-2xl font-bold text-white">{data.total_persons}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <Globe size={18} />
            <span className="text-sm font-medium">Total Sources</span>
          </div>
          <p className="text-2xl font-bold text-white">{data.total_sources}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <TrendingUp size={18} />
            <span className="text-sm font-medium">Total Discoveries</span>
          </div>
          <p className="text-2xl font-bold text-white">{data.total_discoveries}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <BarChart3 size={18} />
            <span className="text-sm font-medium">Avg Confidence</span>
          </div>
          <p className="text-2xl font-bold text-white">
            {typeof data.avg_confidence_score === "number"
              ? `${(data.avg_confidence_score * 100).toFixed(1)}%`
              : "—"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Discovery trend chart (last 30 days) */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
            Discoveries (Last 30 Days)
          </h2>
          <div className="h-48 flex items-end gap-1">
            {discoveries.length === 0 ? (
              <p className="text-gray-500 text-sm">No data</p>
            ) : (
              discoveries.map((d) => (
                <div
                  key={d.date}
                  className="flex-1 flex flex-col items-center gap-1 min-w-0"
                  title={`${d.date}: ${d.count}`}
                >
                  <div
                    className="w-full rounded-t bg-gradient-to-t from-blue-600 to-blue-400 transition-all min-h-[4px]"
                    style={{
                      height: `${Math.max((d.count / maxDiscoveries) * 100, 2)}%`,
                    }}
                  />
                  <span className="text-[10px] text-gray-500 truncate w-full text-center">
                    {new Date(d.date).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Source distribution */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
            Source Distribution
          </h2>
          {sourceDist.length === 0 ? (
            <p className="text-gray-500 text-sm">No data</p>
          ) : (
            <div className="space-y-3">
              {sourceDist.map((s) => (
                <div key={s.platform} className="flex items-center gap-3">
                  <span className="w-24 text-sm text-gray-400 truncate">{s.platform}</span>
                  <div className="flex-1 h-6 rounded bg-white/5 overflow-hidden">
                    <div
                      className="h-full rounded bg-gradient-to-r from-violet-500 to-purple-600 transition-all"
                      style={{
                        width: `${Math.max((s.count / maxSource) * 100, 2)}%`,
                      }}
                    />
                  </div>
                  <span className="w-12 text-right text-sm text-gray-400">{s.count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top companies */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Building size={16} />
            Top Searched Companies
          </h2>
          {topCompanies.length === 0 ? (
            <p className="text-gray-500 text-sm">No data</p>
          ) : (
            <ol className="space-y-2">
              {topCompanies.map((c, i) => (
                <li key={c.company} className="flex items-center gap-3">
                  <span className="w-6 text-sm font-mono text-gray-500">{i + 1}.</span>
                  <span className="flex-1 text-white truncate">{c.company}</span>
                  <span className="text-sm text-gray-400">{c.count}</span>
                </li>
              ))}
            </ol>
          )}
        </div>

        {/* Status breakdown */}
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
            Discoveries by Status
          </h2>
          {statusBreakdown.length === 0 ? (
            <p className="text-gray-500 text-sm">No data</p>
          ) : (
            <ul className="space-y-2">
              {statusBreakdown.map((s) => (
                <li key={s.status} className="flex items-center gap-3">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor: STATUS_COLORS[s.status] ?? "#6b7280",
                    }}
                  />
                  <span className="flex-1 text-white capitalize">{s.status.replace(/_/g, " ")}</span>
                  <span className="text-sm text-gray-400">{s.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

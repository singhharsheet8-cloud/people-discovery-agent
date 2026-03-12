"use client";

import { useState, useEffect } from "react";
import { DollarSign, Zap, TrendingUp, BarChart3 } from "lucide-react";
import { getCostStats } from "@/lib/api";
import type { CostStats } from "@/lib/types";

export default function CostDashboardPage() {
  const [stats, setStats] = useState<CostStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getCostStats()
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch(() => {
        if (!cancelled) setStats(null);
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
        Loading...
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-red-400">
        Failed to load cost stats
      </div>
    );
  }

  const recentJobs = stats.recent_jobs ?? [];

  const maxCost =
    Math.max(...recentJobs.map((j) => j.total_cost), 0.001) || 0.001;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <BarChart3 size={24} />
        Cost Dashboard
      </h1>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <DollarSign size={18} />
            <span className="text-sm font-medium">Total Spend</span>
          </div>
          <p className="text-2xl font-bold text-white">
            ${stats.total_spend.toFixed(4)}
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <Zap size={18} />
            <span className="text-sm font-medium">Total Jobs</span>
          </div>
          <p className="text-2xl font-bold text-white">{stats.total_jobs}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <div className="flex items-center gap-2 text-gray-400 mb-2">
            <TrendingUp size={18} />
            <span className="text-sm font-medium">Avg Cost / Discovery</span>
          </div>
          <p className="text-2xl font-bold text-white">
            ${stats.average_cost.toFixed(4)}
          </p>
        </div>
      </div>

      {/* Bar chart - recent jobs by cost */}
      {recentJobs.length > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
            Recent Jobs by Cost
          </h2>
          <div className="space-y-3">
            {recentJobs.map((j) => (
              <div key={j.id} className="flex items-center gap-4">
                <span className="w-24 text-xs font-mono text-gray-500 truncate">
                  {j.id.slice(0, 8)}...
                </span>
                <div className="flex-1 h-6 rounded bg-white/5 overflow-hidden">
                  <div
                    className="h-full rounded bg-gradient-to-r from-blue-500 to-purple-600 transition-all"
                    style={{
                      width: `${Math.max(
                        (j.total_cost / maxCost) * 100,
                        2
                      )}%`,
                    }}
                  />
                </div>
                <span className="w-20 text-right text-sm text-gray-400">
                  ${j.total_cost.toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent jobs table */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider p-4 border-b border-white/10">
          Recent Jobs
        </h2>
        {recentJobs.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No jobs yet</div>
        ) : (
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
                    Sources Hit
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Cache Hits
                  </th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((j) => (
                  <tr
                    key={j.id}
                    className="border-b border-white/5 hover:bg-white/5"
                  >
                    <td className="py-3 px-4 text-gray-400 font-mono text-xs">
                      {j.id.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-4 text-white">
                      ${j.total_cost.toFixed(4)}
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
                        ? new Date(j.created_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

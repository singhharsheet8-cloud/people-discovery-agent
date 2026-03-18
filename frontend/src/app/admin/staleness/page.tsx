"use client";

import { useState, useEffect, useCallback } from "react";
import {
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Users,
  Zap,
  Calendar,
  Play,
} from "lucide-react";
import { getStalenessStatus, triggerStalenessRefresh } from "@/lib/api";

interface StalenessData {
  total_persons: number;
  stale_count: number;
  stale_after_days: number;
  refresh_cooldown_days: number;
  batch_size: number;
  cron_interval_seconds: number;
  oldest_profiles: Array<{ name: string; updated_at: string | null }>;
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  accent?: "red" | "yellow" | "green" | "brand";
}) {
  const colors = {
    red: "text-red-400 bg-red-500/10 border-red-500/20",
    yellow: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
    green: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    brand: "text-brand-400 bg-brand-500/10 border-brand-500/20",
  };
  const cls = accent ? colors[accent] : "text-gray-300 bg-white/5 border-white/10";

  return (
    <div className={`rounded-xl border p-5 ${cls}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider opacity-70 mb-1">{label}</p>
          <p className="text-3xl font-bold">{value}</p>
          {sub && <p className="text-xs mt-1 opacity-60">{sub}</p>}
        </div>
        <Icon size={22} className="opacity-60 mt-1 shrink-0" />
      </div>
    </div>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  if (d > 0) return `${d}d ${h}h ago`;
  const m = Math.floor(diff / 60000);
  return `${m}m ago`;
}

export default function StalenessPage() {
  const [data, setData] = useState<StalenessData | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await getStalenessStatus();
      setData(d);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleTrigger = async () => {
    setTriggering(true);
    setTriggerMsg("");
    try {
      const r = await triggerStalenessRefresh();
      setTriggerMsg(r.message || "Refresh triggered");
      setTimeout(() => load(), 3000);
    } catch {
      setTriggerMsg("Failed to trigger refresh");
    } finally {
      setTriggering(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center min-h-[300px] text-gray-500">
      Loading...
    </div>
  );

  const stalePct = data && data.total_persons > 0
    ? Math.round((data.stale_count / data.total_persons) * 100)
    : 0;

  const cronHours = data ? Math.round(data.cron_interval_seconds / 3600) : 0;

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Clock size={24} className="text-brand-400" /> Profile Staleness
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Auto-refresh detects outdated profiles and re-queues discovery every {cronHours}h
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={load}
            className="flex items-center gap-2 text-gray-500 hover:text-gray-300 text-sm transition-colors"
          >
            <RefreshCw size={14} /> Refresh
          </button>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {triggering ? (
              <><RefreshCw size={14} className="animate-spin" /> Running…</>
            ) : (
              <><Play size={14} /> Run now</>
            )}
          </button>
        </div>
      </div>

      {triggerMsg && (
        <div className="bg-brand-500/10 border border-brand-500/20 rounded-xl px-4 py-3 text-sm text-brand-400">
          {triggerMsg}
        </div>
      )}

      {/* Stats grid */}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              icon={Users}
              label="Total Profiles"
              value={data.total_persons}
              accent="brand"
            />
            <StatCard
              icon={AlertTriangle}
              label="Stale Profiles"
              value={data.stale_count}
              sub={`${stalePct}% of total`}
              accent={stalePct > 50 ? "red" : stalePct > 20 ? "yellow" : "green"}
            />
            <StatCard
              icon={Calendar}
              label="Stale After"
              value={`${data.stale_after_days}d`}
              sub="configurable via env"
            />
            <StatCard
              icon={Zap}
              label="Batch Size"
              value={data.batch_size}
              sub={`per ${cronHours}h cron tick`}
            />
          </div>

          {/* Overall health bar */}
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-white">Profile Freshness</span>
              <span className="text-xs text-gray-500">
                {data.total_persons - data.stale_count} fresh / {data.stale_count} stale
              </span>
            </div>
            <div className="h-3 bg-white/5 rounded-full overflow-hidden flex">
              <div
                className="h-full bg-emerald-500 transition-all duration-700"
                style={{ width: `${100 - stalePct}%` }}
              />
              <div
                className="h-full bg-red-500/80 transition-all duration-700"
                style={{ width: `${stalePct}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-600">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
                Fresh (updated within {data.stale_after_days}d)
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
                Stale (needs refresh)
              </span>
            </div>
          </div>

          {/* Oldest profiles */}
          {data.oldest_profiles.length > 0 && (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] overflow-hidden">
              <div className="px-5 py-4 border-b border-white/10">
                <h3 className="text-sm font-semibold text-white">Oldest Profiles</h3>
                <p className="text-xs text-gray-500 mt-0.5">These will be refreshed first in the next cron tick</p>
              </div>
              <div className="divide-y divide-white/5">
                {data.oldest_profiles.map((p, i) => {
                  const ago = timeAgo(p.updated_at);
                  const days = p.updated_at
                    ? Math.floor((Date.now() - new Date(p.updated_at).getTime()) / 86400000)
                    : 999;
                  const isStale = days >= data.stale_after_days;
                  return (
                    <div key={i} className="flex items-center justify-between px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full shrink-0 ${isStale ? "bg-red-500" : "bg-emerald-500"}`} />
                        <span className="text-sm text-white font-medium">{p.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        {isStale && (
                          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 border border-red-500/20">
                            stale
                          </span>
                        )}
                        <span className="text-xs text-gray-500 font-mono">{ago}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Config summary */}
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Configuration</h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
              {[
                ["STALE_AFTER_DAYS", `${data.stale_after_days} days`],
                ["REFRESH_COOLDOWN_DAYS", `${data.refresh_cooldown_days} days`],
                ["STALENESS_BATCH_SIZE", `${data.batch_size} persons/tick`],
                ["STALENESS_CRON_INTERVAL", `${data.cron_interval_seconds}s (${cronHours}h)`],
              ].map(([key, val]) => (
                <div key={key} className="flex flex-col gap-0.5">
                  <code className="text-gray-500">{key}</code>
                  <span className="text-gray-300 font-medium">{val}</span>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600 mt-3">
              Set these environment variables on Railway to tune the refresh schedule.
            </p>
          </div>

          {/* All fresh state */}
          {data.stale_count === 0 && (
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6 text-center">
              <CheckCircle2 size={32} className="mx-auto text-emerald-400 mb-2" />
              <p className="text-emerald-400 font-semibold">All profiles are fresh!</p>
              <p className="text-emerald-600 text-sm mt-1">
                No person has been updated more than {data.stale_after_days} days ago.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

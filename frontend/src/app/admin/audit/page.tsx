"use client";

import { useState, useEffect } from "react";
import { Shield, Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import { getAuditLog } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";

const ACTION_OPTIONS = [
  { value: "", label: "All actions" },
  { value: "discover", label: "Discover" },
  { value: "view", label: "View" },
  { value: "edit", label: "Edit" },
  { value: "delete", label: "Delete" },
  { value: "export", label: "Export" },
  { value: "share", label: "Share" },
];

const ACTION_BADGE_COLORS: Record<string, string> = {
  discover: "bg-blue-500/20 text-blue-400",
  view: "bg-gray-500/20 text-gray-400",
  edit: "bg-amber-500/20 text-amber-400",
  delete: "bg-red-500/20 text-red-400",
  export: "bg-emerald-500/20 text-emerald-400",
  share: "bg-violet-500/20 text-violet-400",
};

function getActionBadgeClass(action: string): string {
  const key = action.toLowerCase();
  return ACTION_BADGE_COLORS[key] ?? "bg-white/10 text-gray-400";
}

export default function AuditLogPage() {
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [actionFilter, setActionFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAuditLog(page, perPage, actionFilter || undefined)
      .then((res) => {
        if (!cancelled) {
          setItems(res.items ?? []);
          setTotal(res.total ?? 0);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [page, perPage, actionFilter]);

  const totalPages = Math.ceil(total / perPage);

  function formatTime(s: string) {
    return new Date(s).toLocaleString(undefined, {
      dateStyle: "short",
      timeStyle: "medium",
    });
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <Shield size={24} />
        Audit Log
      </h1>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-400">Action:</label>
          <select
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setPage(1);
            }}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {ACTION_OPTIONS.map(({ value, label }) => (
              <option key={value || "all"} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={32} className="animate-spin text-gray-500" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center text-gray-500">No audit entries</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Time</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">User</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Action</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Target</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">Details</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">IP</th>
                </tr>
              </thead>
              <tbody>
                {items.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-white/5 hover:bg-white/5"
                  >
                    <td className="py-3 px-4 text-gray-500 whitespace-nowrap">
                      {formatTime(entry.created_at)}
                    </td>
                    <td className="py-3 px-4 text-gray-400">{entry.user_email}</td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${getActionBadgeClass(
                          entry.action
                        )}`}
                      >
                        {entry.action}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {entry.target_type}
                      {entry.target_id && (
                        <span className="text-gray-500 ml-1">({entry.target_id.slice(0, 8)}…)</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-500 max-w-xs truncate">
                      {entry.details ?? "—"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 font-mono text-xs">
                      {entry.ip_address ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-white/10">
            <span className="text-sm text-gray-500">
              Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, total)} of {total}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg border border-white/10 text-gray-400 hover:text-white hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={18} />
              </button>
              <span className="text-sm text-gray-400">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg border border-white/10 text-gray-400 hover:text-white hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

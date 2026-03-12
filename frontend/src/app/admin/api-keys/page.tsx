"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, Copy, CheckCircle } from "lucide-react";

interface ApiKeyItem {
  id: string;
  name: string;
  key?: string;
  rate_limit_per_day: number;
  active: boolean;
  usage_count: number;
  total_cost: number;
  last_used_at: string | null;
  created_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined"
    ? (localStorage.getItem("access_token") || localStorage.getItem("admin_token"))
    : null;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyLimit, setNewKeyLimit] = useState(100);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchKeys();
  }, []);

  async function fetchKeys() {
    try {
      const res = await fetch(`${API_BASE}/api-keys`, { headers: getAuthHeaders() });
      const data = await res.json();
      setKeys(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function createKey() {
    if (!newKeyName.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api-keys`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify({ name: newKeyName, rate_limit_per_day: newKeyLimit }),
      });
      if (!res.ok) return;
      const data = await res.json();
      setCreatedKey(data.key);
      setNewKeyName("");
      fetchKeys();
    } catch (e) {
      console.error(e);
    }
  }

  async function revokeKey(id: string) {
    if (!confirm("Revoke this API key?")) return;
    try {
      await fetch(`${API_BASE}/api-keys/${id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      fetchKeys();
    } catch (e) {
      console.error(e);
    }
  }

  function copyKey() {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">API Key Management</h1>

      {/* Create new key */}
      <div className="bg-white/5 rounded-xl border border-white/10 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Create New Key</h2>
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="text-sm text-gray-400 block mb-1">Key Name</label>
            <input
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="e.g., Production API"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="w-40">
            <label className="text-sm text-gray-400 block mb-1">Rate Limit/Day</label>
            <input
              type="number"
              value={newKeyLimit}
              onChange={(e) => setNewKeyLimit(parseInt(e.target.value) || 100)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={createKey}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Plus size={16} /> Create
          </button>
        </div>

        {createdKey && (
          <div className="mt-4 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
            <p className="text-sm text-emerald-400 mb-2">
              Key created! Copy it now — it won&apos;t be shown again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-black/30 rounded px-3 py-2 text-sm text-white font-mono">
                {createdKey}
              </code>
              <button
                onClick={copyKey}
                className="p-2 rounded-lg hover:bg-white/10 text-gray-400"
              >
                {copied ? (
                  <CheckCircle size={16} className="text-emerald-400" />
                ) : (
                  <Copy size={16} />
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Key list */}
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-left text-gray-400">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Rate Limit</th>
              <th className="px-4 py-3">Usage</th>
              <th className="px-4 py-3">Cost</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Last Used</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} className="border-b border-white/5 hover:bg-white/5">
                <td className="px-4 py-3 text-white font-medium">{k.name}</td>
                <td className="px-4 py-3 text-gray-300">{k.rate_limit_per_day}/day</td>
                <td className="px-4 py-3 text-gray-300">{k.usage_count} requests</td>
                <td className="px-4 py-3 text-gray-300">${(k.total_cost ?? 0).toFixed(4)}</td>
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      k.active ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
                    }`}
                  >
                    {k.active ? "Active" : "Revoked"}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "Never"}
                </td>
                <td className="px-4 py-3">
                  {k.active && (
                    <button
                      onClick={() => revokeKey(k.id)}
                      className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {keys.length === 0 && !loading && (
          <div className="text-center py-8 text-gray-500">No API keys yet</div>
        )}
      </div>
    </div>
  );
}

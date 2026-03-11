"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react";

interface WebhookItem {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  created_at: string;
}

interface WebhookDelivery {
  id: string;
  event: string;
  status_code: number | null;
  success: boolean;
  attempts: number;
  created_at: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const WEBHOOK_EVENTS = ["job.completed", "job.failed", "person.updated"];

function getAuthHeaders(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export default function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [newUrl, setNewUrl] = useState("");
  const [newEvents, setNewEvents] = useState<string[]>(["job.completed"]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDelivery[]>>({});

  useEffect(() => {
    fetchWebhooks();
  }, []);

  async function fetchWebhooks() {
    try {
      const res = await fetch(`${API_BASE}/webhooks`, { headers: getAuthHeaders() });
      const data = await res.json();
      setWebhooks(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function createWebhook() {
    if (!newUrl.trim()) return;
    try {
      await fetch(`${API_BASE}/webhooks`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: JSON.stringify({ url: newUrl.trim(), events: newEvents }),
      });
      setNewUrl("");
      setNewEvents(["job.completed"]);
      fetchWebhooks();
    } catch (e) {
      console.error(e);
    }
  }

  async function deleteWebhook(id: string) {
    if (!confirm("Deactivate this webhook?")) return;
    try {
      await fetch(`${API_BASE}/webhooks/${id}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
      });
      fetchWebhooks();
    } catch (e) {
      console.error(e);
    }
  }

  async function toggleDeliveries(id: string) {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/webhooks/${id}/deliveries`, {
        headers: getAuthHeaders(),
      });
      const data = await res.json();
      setDeliveries((prev) => ({ ...prev, [id]: data }));
      setExpandedId(id);
    } catch (e) {
      console.error(e);
    }
  }

  function toggleEvent(event: string) {
    setNewEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Webhook Management</h1>

      {/* Create new webhook */}
      <div className="bg-white/5 rounded-xl border border-white/10 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Create New Webhook</h2>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">URL</label>
            <input
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://your-server.com/webhook"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-2">Events</label>
            <div className="flex flex-wrap gap-2">
              {WEBHOOK_EVENTS.map((ev) => (
                <label
                  key={ev}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 cursor-pointer hover:bg-white/10"
                >
                  <input
                    type="checkbox"
                    checked={newEvents.includes(ev)}
                    onChange={() => toggleEvent(ev)}
                    className="rounded border-white/20"
                  />
                  <span className="text-sm text-gray-300">{ev}</span>
                </label>
              ))}
            </div>
          </div>
          <button
            onClick={createWebhook}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Plus size={16} /> Create
          </button>
        </div>
      </div>

      {/* Webhook list */}
      <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
        <div className="divide-y divide-white/10">
          {webhooks.map((w) => (
            <div key={w.id} className="p-4 hover:bg-white/5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{w.url}</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {w.events.map((e) => (
                      <span
                        key={e}
                        className="px-2 py-0.5 rounded text-xs bg-white/10 text-gray-400"
                      >
                        {e}
                      </span>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Created {new Date(w.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleDeliveries(w.id)}
                    className="flex items-center gap-1 px-2 py-1 rounded text-sm text-gray-400 hover:text-white hover:bg-white/10"
                  >
                    {expandedId === w.id ? (
                      <ChevronUp size={14} />
                    ) : (
                      <ChevronDown size={14} />
                    )}
                    History
                  </button>
                  <button
                    onClick={() => deleteWebhook(w.id)}
                    className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              {expandedId === w.id && deliveries[w.id] && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <p className="text-xs text-gray-500 mb-2">Recent deliveries</p>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {deliveries[w.id].length === 0 ? (
                      <p className="text-sm text-gray-500">No deliveries yet</p>
                    ) : (
                      deliveries[w.id].map((d) => (
                        <div
                          key={d.id}
                          className="flex items-center justify-between text-sm py-1 px-2 rounded bg-black/20"
                        >
                          <span className="text-gray-400">{d.event}</span>
                          <span
                            className={
                              d.success ? "text-emerald-400" : "text-red-400"
                            }
                          >
                            {d.success ? "✓" : "✗"} {d.status_code ?? "—"}
                          </span>
                          <span className="text-gray-500 text-xs">
                            {new Date(d.created_at).toLocaleString()}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        {webhooks.length === 0 && !loading && (
          <div className="text-center py-8 text-gray-500">No webhooks yet</div>
        )}
      </div>
    </div>
  );
}

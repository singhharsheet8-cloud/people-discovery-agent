"use client";

import { useState, useEffect } from "react";
import { History, Clock, Trash2, Search, ChevronRight } from "lucide-react";
import { cn, confidenceColor } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface SessionSummary {
  session_id: string;
  query: string;
  status: string;
  confidence_score: number;
  created_at: string;
}

interface SessionHistoryProps {
  onLoadSession: (sessionId: string) => void;
  currentSessionId: string | null;
}

export function SessionHistory({ onLoadSession, currentSessionId }: SessionHistoryProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchSessions = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_URL}/sessions?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch {
      // API unavailable
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const deleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await fetch(`${API_URL}/sessions/${sessionId}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch {
      // ignore
    }
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return d.toLocaleDateString();
  };

  const statusLabel = (status: string) => {
    const map: Record<string, string> = {
      complete: "Complete",
      in_progress: "In Progress",
      awaiting_clarification: "Needs Input",
      error: "Error",
      created: "Created",
    };
    return map[status] || status;
  };

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={16} className="text-gray-500" />
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">History</span>
          </div>
          <button
            onClick={fetchSessions}
            className="p-1 rounded text-gray-500 hover:text-gray-300 transition-colors"
            title="Refresh"
          >
            <Search size={14} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading && sessions.length === 0 && (
          <div className="p-4 text-center text-xs text-gray-600">Loading...</div>
        )}

        {!isLoading && sessions.length === 0 && (
          <div className="p-4 text-center text-xs text-gray-600">No sessions yet</div>
        )}

        {sessions.map((session) => (
          <button
            key={session.session_id}
            onClick={() => onLoadSession(session.session_id)}
            className={cn(
              "w-full text-left p-3 border-b border-white/5 group transition-colors",
              session.session_id === currentSessionId
                ? "bg-brand-500/10 border-l-2 border-l-brand-500"
                : "hover:bg-white/5",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-300 truncate">{session.query}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={cn("text-[10px] font-medium", confidenceColor(session.confidence_score))}>
                    {session.status === "complete"
                      ? `${Math.round(session.confidence_score * 100)}%`
                      : statusLabel(session.status)}
                  </span>
                  <span className="text-[10px] text-gray-600 flex items-center gap-0.5">
                    <Clock size={9} />
                    {session.created_at ? formatDate(session.created_at) : ""}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => deleteSession(e, session.session_id)}
                  className="p-1 rounded text-gray-600 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={12} />
                </button>
                <ChevronRight size={14} className="text-gray-600" />
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

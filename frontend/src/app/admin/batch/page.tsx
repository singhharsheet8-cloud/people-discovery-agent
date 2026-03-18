"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  Upload,
  Play,
  CheckCircle,
  XCircle,
  Loader2,
  Download,
  FileText,
  RefreshCw,
  Users,
  Clock,
  RotateCcw,
} from "lucide-react";
import { batchDiscover, discoverPerson, getJob } from "@/lib/api";
import type { DiscoverRequest } from "@/lib/types";

// Step labels in order — matches backend _STEP_LABELS
const STEP_ORDER = [
  "planning",
  "searching",
  "disambiguating",
  "filtering",
  "analyzing",
  "enriching",
  "scoring_sentiment",
  "synthesizing",
  "verifying",
] as const;
type StepKey = (typeof STEP_ORDER)[number];

const STEP_LABEL: Record<StepKey, string> = {
  planning: "Planning",
  searching: "Searching",
  disambiguating: "Verifying identity",
  filtering: "Filtering",
  analyzing: "Analyzing",
  enriching: "Enriching",
  scoring_sentiment: "Scoring",
  synthesizing: "Synthesizing",
  verifying: "Verifying facts",
};

interface BatchRow extends DiscoverRequest {
  _status: "pending" | "running" | "completed" | "failed";
  _jobId: string;
  _error: string;
  _step: string;
  _elapsedSec: number;
  _startedAt: number;
}

const CSV_TEMPLATE =
  "name,company,role,location,linkedin_url,twitter_handle,github_username,instagram_handle,context\n" +
  "Jane Smith,Acme Corp,CTO,San Francisco,,@janesmith,janesmith,,AI researcher\n" +
  "John Doe,BigCo,VP Engineering,New York,https://www.linkedin.com/in/johndoe,,,johndoe,";

function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (const ch of line) {
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === "," && !inQuotes) {
      result.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current);
  return result;
}

function StepProgressBar({ step, status }: { step: string; status: BatchRow["_status"] }) {
  if (status === "pending") return <span className="text-xs text-gray-600">Queued</span>;
  if (status === "completed") return (
    <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-medium">
      <CheckCircle size={12} /> Completed
    </div>
  );
  if (status === "failed") return (
    <div className="flex items-center gap-1.5 text-red-400 text-xs font-medium">
      <XCircle size={12} /> Failed
    </div>
  );

  // running
  const stepIdx = STEP_ORDER.indexOf(step as StepKey);
  const pct = stepIdx >= 0
    ? Math.round(((stepIdx + 1) / STEP_ORDER.length) * 100)
    : 5;
  const label = STEP_LABEL[step as StepKey] ?? step ?? "Starting…";

  return (
    <div className="space-y-1 min-w-[140px]">
      <div className="flex items-center justify-between">
        <span className="text-xs text-brand-400 font-medium flex items-center gap-1">
          <Loader2 size={10} className="animate-spin" />
          {label}
        </span>
        <span className="text-[10px] text-gray-600 font-mono">{pct}%</span>
      </div>
      <div className="h-1 bg-white/10 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-purple-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function BatchPage() {
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const tickRef = useRef<NodeJS.Timeout | null>(null);

  // Tick elapsed seconds for running rows
  useEffect(() => {
    tickRef.current = setInterval(() => {
      setRows((prev) => {
        const hasRunning = prev.some((r) => r._status === "running");
        if (!hasRunning) return prev;
        return prev.map((r) =>
          r._status === "running" && r._startedAt
            ? { ...r, _elapsedSec: Math.floor((Date.now() - r._startedAt) / 1000) }
            : r
        );
      });
    }, 1000);
    return () => { if (tickRef.current) clearInterval(tickRef.current); };
  }, []);

  function handleCSVUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    if (e.target) e.target.value = "";

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const lines = text.trim().split(/\r?\n/);
      if (lines.length < 2) { setError("CSV must have a header row and at least one data row"); return; }

      const headers = lines[0].split(",").map((h) => h.trim().toLowerCase().replace(/^"/, "").replace(/"$/, ""));
      const nameIdx = headers.indexOf("name");
      if (nameIdx === -1) { setError("CSV must have a 'name' column"); return; }

      const parsed: BatchRow[] = [];
      for (let i = 1; i < lines.length; i++) {
        const cols = parseCSVLine(lines[i]);
        const name = cols[nameIdx]?.trim().replace(/^"/, "").replace(/"$/, "");
        if (!name) continue;
        parsed.push({
          name,
          company: cols[headers.indexOf("company")]?.trim() || "",
          role: cols[headers.indexOf("role")]?.trim() || "",
          location: cols[headers.indexOf("location")]?.trim() || "",
          linkedin_url: cols[headers.indexOf("linkedin_url")]?.trim() || "",
          twitter_handle: cols[headers.indexOf("twitter_handle")]?.trim() || "",
          github_username: cols[headers.indexOf("github_username")]?.trim() || "",
          instagram_handle: cols[headers.indexOf("instagram_handle")]?.trim() || "",
          context: cols[headers.indexOf("context")]?.trim() || "",
          _status: "pending",
          _jobId: "",
          _error: "",
          _step: "",
          _elapsedSec: 0,
          _startedAt: 0,
        });
      }

      if (parsed.length === 0) { setError("No valid rows found in CSV"); return; }
      if (parsed.length > 50) { setError("Maximum 50 people per batch. Split your CSV."); return; }
      setRows(parsed);
    };
    reader.readAsText(file);
  }

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      setRows((prev) => {
        const allDone = prev.every((r) => r._status === "completed" || r._status === "failed");
        if (allDone && prev.length > 0) {
          if (pollRef.current) clearInterval(pollRef.current);
          setRunning(false);
        }
        return prev;
      });

      // Poll each running job
      setRows((snapshot) => snapshot); // trigger read
      // We need to read current rows directly — use a ref pattern
    }, 2500);
  }, []);

  // Use a ref to hold latest rows so the interval can read them
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  const startPollingWithRef = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const current = rowsRef.current;
      const runningRows = current.filter((r) => r._status === "running" && r._jobId);
      if (runningRows.length === 0) {
        const allDone = current.every((r) => r._status === "completed" || r._status === "failed");
        if (allDone && current.length > 0) {
          if (pollRef.current) clearInterval(pollRef.current);
          setRunning(false);
        }
        return;
      }

      await Promise.allSettled(
        runningRows.map(async (row) => {
          try {
            const job = await getJob(row._jobId);
            setRows((prev) =>
              prev.map((r) => {
                if (r._jobId !== row._jobId) return r;
                if (job.status === "completed") return { ...r, _status: "completed", _step: "" };
                if (job.status === "failed") return { ...r, _status: "failed", _error: job.error_message || "Failed", _step: "" };
                if (job.current_step) return { ...r, _step: job.current_step };
                return r;
              })
            );
          } catch { /* keep polling */ }
        })
      );
    }, 2500);
  }, []);

  useEffect(() => { startPolling; return () => { if (pollRef.current) clearInterval(pollRef.current); }; }, [startPolling]);

  async function handleStart() {
    if (rows.length === 0) return;
    const toRun = rows.filter((r) => r._status === "pending" || r._status === "failed");
    if (toRun.length === 0) return;
    setRunning(true);
    setError("");

    try {
      const people: DiscoverRequest[] = toRun.map(({ _status, _jobId, _error, _step, _elapsedSec, _startedAt, ...rest }) => rest);
      const res = await batchDiscover(people);
      const jobs = (res.jobs || []) as Array<{ job_id: string }>;
      const now = Date.now();

      let toRunIdx = 0;
      setRows((prev) =>
        prev.map((r) => {
          if (r._status !== "pending" && r._status !== "failed") return r;
          const job = jobs[toRunIdx++];
          return {
            ...r,
            _status: "running" as const,
            _jobId: job?.job_id || "",
            _error: "",
            _step: "",
            _elapsedSec: 0,
            _startedAt: now,
          };
        })
      );
      startPollingWithRef();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Batch discovery failed");
      setRunning(false);
    }
  }

  async function retryFailed() {
    const failed = rows.filter((r) => r._status === "failed");
    if (failed.length === 0) return;
    setRunning(true);
    setError("");
    const now = Date.now();

    try {
      const people: DiscoverRequest[] = failed.map(({ _status, _jobId, _error, _step, _elapsedSec, _startedAt, ...rest }) => rest);
      const res = await batchDiscover(people);
      const jobs = (res.jobs || []) as Array<{ job_id: string }>;
      let idx = 0;
      setRows((prev) =>
        prev.map((r) => {
          if (r._status !== "failed") return r;
          const job = jobs[idx++];
          return { ...r, _status: "running" as const, _jobId: job?.job_id || "", _error: "", _step: "", _elapsedSec: 0, _startedAt: now };
        })
      );
      startPollingWithRef();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry failed");
      setRunning(false);
    }
  }

  void discoverPerson; // keep import live

  function downloadTemplate() {
    const blob = new Blob([CSV_TEMPLATE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "batch_discovery_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function resetAll() {
    if (pollRef.current) clearInterval(pollRef.current);
    setRows([]);
    setRunning(false);
    setError("");
  }

  const total = rows.length;
  const completed = rows.filter((r) => r._status === "completed").length;
  const failed = rows.filter((r) => r._status === "failed").length;
  const inProgress = rows.filter((r) => r._status === "running").length;
  const pending = rows.filter((r) => r._status === "pending").length;
  const overallPct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const avgElapsed = rows.filter((r) => r._status === "completed" && r._elapsedSec > 0)
    .reduce((a, r, _, arr) => a + r._elapsedSec / arr.length, 0);
  const estRemaining = avgElapsed > 0 && (pending + inProgress) > 0
    ? Math.round(avgElapsed * (pending + inProgress))
    : null;

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Users size={24} className="text-brand-400" /> Batch Discovery
          </h1>
          <p className="text-sm text-gray-500 mt-1">Discover up to 50 people at once from a CSV file</p>
        </div>
        {rows.length > 0 && !running && (
          <button
            onClick={resetAll}
            className="flex items-center gap-2 text-gray-500 hover:text-gray-300 text-sm transition-colors"
          >
            <RotateCcw size={14} /> Reset
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Upload card */}
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Upload CSV</h2>
          <button
            onClick={downloadTemplate}
            className="flex items-center gap-1.5 text-gray-500 hover:text-gray-300 text-xs transition-colors"
          >
            <Download size={12} /> Download template
          </button>
        </div>

        <p className="text-sm text-gray-400">
          Required column: <code className="text-brand-400 bg-brand-500/10 px-1 rounded">name</code>.
          Optional: <code className="text-gray-500">company, role, location, linkedin_url, twitter_handle, github_username, instagram_handle, context</code>
        </p>

        <div className="flex flex-wrap gap-3 items-center">
          <input ref={fileRef} type="file" accept=".csv" onChange={handleCSVUpload} className="hidden" />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={running}
            className="flex items-center gap-2 bg-white/10 hover:bg-white/15 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 border border-white/10"
          >
            <FileText size={15} /> Choose CSV File
          </button>

          {rows.length > 0 && (
            <>
              <button
                onClick={handleStart}
                disabled={running || rows.every((r) => r._status === "completed")}
                className="flex items-center gap-2 bg-gradient-to-r from-brand-500 to-purple-600 hover:from-brand-600 hover:to-purple-700 text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {running ? (
                  <><Loader2 size={15} className="animate-spin" /> Running…</>
                ) : (
                  <><Play size={15} /> Discover {rows.filter(r => r._status === "pending" || r._status === "failed").length} People</>
                )}
              </button>

              {failed > 0 && !running && (
                <button
                  onClick={retryFailed}
                  className="flex items-center gap-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors border border-red-500/20"
                >
                  <RefreshCw size={14} /> Retry {failed} Failed
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Progress summary bar */}
      {total > 0 && (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-5 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-4">
              <span className="text-white font-medium">{completed}/{total} completed</span>
              {inProgress > 0 && (
                <span className="text-brand-400 flex items-center gap-1">
                  <Loader2 size={12} className="animate-spin" /> {inProgress} running
                </span>
              )}
              {failed > 0 && <span className="text-red-400">{failed} failed</span>}
              {pending > 0 && !running && <span className="text-gray-500">{pending} pending</span>}
            </div>
            <div className="flex items-center gap-3 text-gray-500 text-xs">
              {estRemaining !== null && running && (
                <span className="flex items-center gap-1">
                  <Clock size={11} /> ~{estRemaining}s remaining
                </span>
              )}
              <span className="font-mono">{overallPct}%</span>
            </div>
          </div>
          <div className="h-2 bg-white/5 rounded-full overflow-hidden flex">
            <div
              className="h-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${overallPct}%` }}
            />
            {failed > 0 && (
              <div
                className="h-full bg-red-500 transition-all duration-500"
                style={{ width: `${Math.round((failed / total) * 100)}%` }}
              />
            )}
          </div>
        </div>
      )}

      {/* Rows table */}
      {rows.length > 0 && (
        <div className="rounded-xl border border-white/10 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left bg-white/[0.02]">
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-8">#</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Company</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Role</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Progress</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-16">Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  className={`border-b border-white/5 transition-colors ${
                    row._status === "running" ? "bg-brand-500/[0.04]" :
                    row._status === "completed" ? "bg-emerald-500/[0.03]" :
                    row._status === "failed" ? "bg-red-500/[0.03]" :
                    "hover:bg-white/[0.02]"
                  }`}
                >
                  <td className="px-4 py-3.5 text-gray-600 text-xs font-mono">{i + 1}</td>
                  <td className="px-4 py-3.5 text-white font-medium">{row.name}</td>
                  <td className="px-4 py-3.5 text-gray-400">{row.company || "—"}</td>
                  <td className="px-4 py-3.5 text-gray-400">{row.role || "—"}</td>
                  <td className="px-4 py-3.5">
                    <StepProgressBar step={row._step} status={row._status} />
                    {row._status === "failed" && row._error && (
                      <p className="text-[10px] text-red-400 mt-1 truncate max-w-[200px]" title={row._error}>
                        {row._error}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3.5 text-gray-600 text-xs font-mono">
                    {row._elapsedSec > 0 ? `${row._elapsedSec}s` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-16 text-center">
          <Upload size={40} className="mx-auto text-gray-700 mb-4" />
          <p className="text-gray-500 text-sm">Upload a CSV to get started</p>
          <p className="text-gray-600 text-xs mt-1">Required column: name. Up to 50 people per batch.</p>
        </div>
      )}
    </div>
  );
}

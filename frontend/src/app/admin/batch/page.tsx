"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { Upload, Play, CheckCircle, XCircle, Loader2, Download, FileText } from "lucide-react";
import { batchDiscover, getJob } from "@/lib/api";
import type { DiscoverRequest } from "@/lib/types";

interface BatchRow extends DiscoverRequest {
  _status?: "pending" | "running" | "completed" | "failed";
  _jobId?: string;
  _error?: string;
}

const CSV_TEMPLATE = "name,company,role,location,linkedin_url,twitter_handle,github_username,instagram_handle,context\nJane Smith,Acme Corp,CTO,San Francisco,,@janesmith,janesmith,,AI researcher\nJohn Doe,BigCo,VP Engineering,New York,https://www.linkedin.com/in/johndoe,,,johndoe,";

export default function BatchPage() {
  const [rows, setRows] = useState<BatchRow[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  function handleCSVUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");

    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const lines = text.trim().split("\n");
      if (lines.length < 2) {
        setError("CSV must have a header row and at least one data row");
        return;
      }

      const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
      const nameIdx = headers.indexOf("name");
      if (nameIdx === -1) {
        setError("CSV must have a 'name' column");
        return;
      }

      const parsed: BatchRow[] = [];
      for (let i = 1; i < lines.length; i++) {
        const cols = parseCSVLine(lines[i]);
        const name = cols[nameIdx]?.trim();
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
        });
      }

      if (parsed.length === 0) {
        setError("No valid rows found in CSV");
        return;
      }
      if (parsed.length > 20) {
        setError("Maximum 20 people per batch. Please split your CSV.");
        return;
      }

      setRows(parsed);
    };
    reader.readAsText(file);
  }

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

  const pollJobs = useCallback(() => {
    pollRef.current = setInterval(async () => {
      setRows((prev) => {
        const runningRows = prev.filter((r) => r._status === "running" && r._jobId);
        if (runningRows.length === 0) {
          if (pollRef.current) clearInterval(pollRef.current);
          setRunning(false);
          return prev;
        }
        return prev;
      });

      const current = rows;
      for (const row of current) {
        if (row._status === "running" && row._jobId) {
          try {
            const job = await getJob(row._jobId);
            if (job.status === "completed") {
              setRows((prev) =>
                prev.map((r) =>
                  r._jobId === row._jobId ? { ...r, _status: "completed" } : r
                )
              );
            } else if (job.status === "failed") {
              setRows((prev) =>
                prev.map((r) =>
                  r._jobId === row._jobId
                    ? { ...r, _status: "failed", _error: job.error_message || "Failed" }
                    : r
                )
              );
            }
          } catch {
            // keep polling
          }
        }
      }
    }, 3000);
  }, [rows]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleStart() {
    if (rows.length === 0) return;
    setRunning(true);
    setError("");

    const people: DiscoverRequest[] = rows.map(({ _status, _jobId, _error, ...rest }) => rest);

    try {
      const res = await batchDiscover(people);
      const jobs = res.jobs || [];
      setRows((prev) =>
        prev.map((row, i) => ({
          ...row,
          _status: "running" as const,
          _jobId: jobs[i]?.job_id || "",
        }))
      );
      pollJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Batch discovery failed");
      setRunning(false);
    }
  }

  function downloadTemplate() {
    const blob = new Blob([CSV_TEMPLATE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "batch_discovery_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const completed = rows.filter((r) => r._status === "completed").length;
  const failed = rows.filter((r) => r._status === "failed").length;
  const pending = rows.filter((r) => r._status === "pending" || r._status === "running").length;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <Upload size={24} /> Batch Discovery
      </h1>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Upload section */}
      <div className="bg-white/5 rounded-xl border border-white/10 p-6 space-y-4">
        <h2 className="text-lg font-semibold text-white">Upload CSV</h2>
        <p className="text-sm text-gray-400">
          Upload a CSV file with up to 20 people to discover. Required column: <code className="text-brand-400">name</code>.
          Optional: <code className="text-gray-500">company, role, location, linkedin_url, twitter_handle, github_username, instagram_handle, context</code>.
        </p>

        <div className="flex gap-4 items-center">
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            onChange={handleCSVUpload}
            className="hidden"
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={running}
            className="flex items-center gap-2 bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            <FileText size={16} /> Choose CSV File
          </button>
          <button
            onClick={downloadTemplate}
            className="flex items-center gap-2 text-gray-400 hover:text-white px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Download size={16} /> Download Template
          </button>
          {rows.length > 0 && !running && (
            <button
              onClick={handleStart}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Play size={16} /> Discover {rows.length} People
            </button>
          )}
        </div>

        {running && (
          <div className="flex items-center gap-3 text-sm">
            <Loader2 size={16} className="animate-spin text-brand-400" />
            <span className="text-gray-300">
              Running... {completed}/{rows.length} completed
              {failed > 0 && <span className="text-red-400"> ({failed} failed)</span>}
            </span>
          </div>
        )}
      </div>

      {/* Results table */}
      {rows.length > 0 && (
        <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
          <div className="px-4 py-3 border-b border-white/10 flex justify-between items-center">
            <span className="text-sm text-gray-400">{rows.length} people queued</span>
            {!running && completed + failed === rows.length && rows.length > 0 && (
              <span className="text-sm text-emerald-400">
                <CheckCircle size={14} className="inline mr-1" />
                Batch complete: {completed} succeeded, {failed} failed
              </span>
            )}
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-gray-400">
                <th className="px-4 py-3 w-8">#</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-b border-white/5 hover:bg-white/5">
                  <td className="px-4 py-3 text-gray-500">{i + 1}</td>
                  <td className="px-4 py-3 text-white font-medium">{row.name}</td>
                  <td className="px-4 py-3 text-gray-300">{row.company || "—"}</td>
                  <td className="px-4 py-3 text-gray-300">{row.role || "—"}</td>
                  <td className="px-4 py-3">
                    {row._status === "pending" && (
                      <span className="text-gray-500">Pending</span>
                    )}
                    {row._status === "running" && (
                      <span className="flex items-center gap-1 text-brand-400">
                        <Loader2 size={14} className="animate-spin" /> Running
                      </span>
                    )}
                    {row._status === "completed" && (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle size={14} /> Done
                      </span>
                    )}
                    {row._status === "failed" && (
                      <span className="flex items-center gap-1 text-red-400" title={row._error}>
                        <XCircle size={14} /> Failed
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

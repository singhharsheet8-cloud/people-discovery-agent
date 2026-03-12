"use client";

import { useState } from "react";
import { Book, Copy, Check, ChevronDown, ChevronRight } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface Endpoint {
  method: string;
  path: string;
  description: string;
  auth: boolean;
  body?: string;
  response?: string;
  params?: string;
}

const ENDPOINTS: Record<string, Endpoint[]> = {
  Discovery: [
    {
      method: "POST",
      path: "/api/discover",
      description: "Start a single-person discovery job. Returns a job ID for polling.",
      auth: false,
      body: `{
  "name": "Satya Nadella",
  "company": "Microsoft",
  "role": "CEO",
  "linkedin_url": "",
  "twitter_handle": "sataborasu",
  "github_username": "",
  "context": ""
}`,
      response: `{
  "job_id": "abc-123-...",
  "status": "running",
  "message": "Discovery started. Poll GET /api/jobs/{job_id} for status."
}`,
    },
    {
      method: "POST",
      path: "/api/discover/batch",
      description: "Start discovery for up to 20 people in one request.",
      auth: false,
      body: `{
  "persons": [
    { "name": "Person A", "company": "Co A" },
    { "name": "Person B", "company": "Co B" }
  ]
}`,
      response: `{
  "jobs": [
    { "job_id": "...", "name": "Person A", "status": "running" },
    { "job_id": "...", "name": "Person B", "status": "running" }
  ],
  "total": 2
}`,
    },
    {
      method: "GET",
      path: "/api/jobs/{job_id}",
      description: "Poll job status. Returns profile when completed.",
      auth: false,
      params: "job_id: UUID of the discovery job",
      response: `{
  "id": "...",
  "status": "completed",
  "person_id": "...",
  "total_cost": 0.0023,
  "latency_ms": 12400,
  "profile": { ... }
}`,
    },
  ],
  Persons: [
    {
      method: "GET",
      path: "/api/persons",
      description: "List all discovered persons with pagination and search.",
      auth: false,
      params: "page (int, default 1), per_page (int, default 20), search (string)",
      response: `{
  "items": [ { "id": "...", "name": "...", "company": "...", ... } ],
  "total": 42,
  "page": 1,
  "per_page": 20
}`,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}",
      description: "Get full person profile with all sources and job history.",
      auth: false,
      params: "person_id: UUID",
    },
    {
      method: "PUT",
      path: "/api/persons/{person_id}",
      description: "Update a person profile (admin only). Creates a version record.",
      auth: true,
      body: `{
  "name": "Updated Name",
  "current_role": "New Role",
  "company": "New Company"
}`,
    },
    {
      method: "DELETE",
      path: "/api/persons/{person_id}",
      description: "Delete a person and all associated data (admin only).",
      auth: true,
    },
    {
      method: "POST",
      path: "/api/persons/{person_id}/re-search",
      description: "Re-run discovery using the person's existing data as input (admin only).",
      auth: true,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}/export",
      description: "Export profile as JSON, CSV, or PDF.",
      auth: false,
      params: "format: json | csv | pdf (default: json)",
    },
  ],
  Authentication: [
    {
      method: "POST",
      path: "/api/auth/login",
      description: "Login with admin credentials. Returns access and refresh tokens.",
      auth: false,
      body: `{
  "email": "admin@example.com",
  "password": "your-password"
}`,
      response: `{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 1800,
  "token_type": "bearer",
  "email": "admin@example.com",
  "role": "admin"
}`,
    },
    {
      method: "POST",
      path: "/api/auth/refresh",
      description: "Refresh an expired access token using a refresh token.",
      auth: false,
      body: `{ "refresh_token": "eyJ..." }`,
      response: `{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_in": 1800
}`,
    },
  ],
  "API Keys": [
    {
      method: "POST",
      path: "/api/api-keys",
      description: "Create a new API key (admin only). Key is shown only once.",
      auth: true,
      body: `{ "name": "My Integration", "rate_limit_per_day": 100 }`,
      response: `{
  "id": "...",
  "name": "My Integration",
  "key": "dk_...",
  "rate_limit_per_day": 100
}`,
    },
    {
      method: "GET",
      path: "/api/api-keys",
      description: "List all API keys with usage stats (admin only).",
      auth: true,
    },
    {
      method: "DELETE",
      path: "/api/api-keys/{key_id}",
      description: "Revoke an API key (admin only).",
      auth: true,
    },
  ],
  Webhooks: [
    {
      method: "POST",
      path: "/api/webhooks",
      description: "Register a webhook endpoint to receive job.completed events (admin only).",
      auth: true,
      body: `{
  "url": "https://your-server.com/webhook",
  "events": ["job.completed"],
  "secret": "optional-signing-secret"
}`,
    },
    {
      method: "GET",
      path: "/api/webhooks",
      description: "List active webhooks (admin only).",
      auth: true,
    },
    {
      method: "DELETE",
      path: "/api/webhooks/{webhook_id}",
      description: "Deactivate a webhook (admin only).",
      auth: true,
    },
  ],
  Admin: [
    {
      method: "GET",
      path: "/api/admin/costs",
      description: "Get cost dashboard stats: total spend, average cost, recent jobs.",
      auth: true,
    },
    {
      method: "POST",
      path: "/api/cache/cleanup",
      description: "Remove expired cache entries (admin only).",
      auth: true,
    },
    {
      method: "GET",
      path: "/api/health",
      description: "Health check endpoint. Returns system status and DB connectivity.",
      auth: false,
      response: `{
  "status": "healthy",
  "version": "2.0.0",
  "database": "ok",
  "timestamp": 1741234567.89
}`,
    },
  ],
};

const methodColors: Record<string, string> = {
  GET: "bg-emerald-500/20 text-emerald-400",
  POST: "bg-blue-500/20 text-blue-400",
  PUT: "bg-amber-500/20 text-amber-400",
  DELETE: "bg-red-500/20 text-red-400",
};

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative group">
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 p-1.5 rounded bg-white/10 text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <pre className="bg-black/40 rounded-lg p-4 text-sm overflow-x-auto">
        <code className="text-gray-300">{code}</code>
      </pre>
    </div>
  );
}

function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-white/10 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors"
      >
        {open ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${methodColors[endpoint.method] || "bg-gray-500/20 text-gray-400"}`}>
          {endpoint.method}
        </span>
        <code className="text-sm text-white font-mono">{endpoint.path}</code>
        {endpoint.auth && (
          <span className="ml-auto px-2 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400">Auth</span>
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/10 pt-3">
          <p className="text-sm text-gray-400">{endpoint.description}</p>

          {endpoint.params && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Parameters</p>
              <p className="text-sm text-gray-400">{endpoint.params}</p>
            </div>
          )}

          {endpoint.auth && (
            <p className="text-xs text-yellow-400/80">
              Requires Authorization: Bearer &lt;token&gt; header
            </p>
          )}

          {endpoint.body && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Request Body</p>
              <CodeBlock code={endpoint.body} language="json" />
            </div>
          )}

          {endpoint.response && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Response Example</p>
              <CodeBlock code={endpoint.response} language="json" />
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-gray-500 mb-1">cURL Example</p>
            <CodeBlock
              code={generateCurl(endpoint)}
              language="bash"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function generateCurl(ep: Endpoint): string {
  let cmd = `curl -X ${ep.method} "${API_BASE}${ep.path.replace(/\{.*?\}/g, "YOUR_ID")}"`;
  if (ep.auth) cmd += ` \\\n  -H "Authorization: Bearer YOUR_TOKEN"`;
  if (ep.body) {
    cmd += ` \\\n  -H "Content-Type: application/json"`;
    cmd += ` \\\n  -d '${ep.body.replace(/\n\s*/g, " ").trim()}'`;
  }
  return cmd;
}

export default function ApiDocsPage() {
  return (
    <div className="space-y-8 max-w-4xl">
      <div className="flex items-center gap-3">
        <Book size={24} className="text-blue-400" />
        <h1 className="text-2xl font-bold text-white">API Documentation</h1>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6">
        <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">Base URL</h2>
        <code className="text-lg text-blue-400 font-mono">{API_BASE}</code>
        <p className="text-sm text-gray-500 mt-3">
          All endpoints return JSON responses. Authentication uses JWT Bearer tokens.
          API keys can be passed via the <code className="text-gray-400">X-API-Key</code> header
          for external integrations (5x higher rate limit).
        </p>
      </div>

      {Object.entries(ENDPOINTS).map(([section, endpoints]) => (
        <div key={section}>
          <h2 className="text-lg font-semibold text-white mb-3">{section}</h2>
          <div className="space-y-2">
            {endpoints.map((ep, i) => (
              <EndpointCard key={`${ep.method}-${ep.path}-${i}`} endpoint={ep} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

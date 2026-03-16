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
      description: "Start a single-person discovery job. Runs the full AI pipeline (plan → search → score → disambiguate → synthesize) and returns a job ID for polling.",
      auth: false,
      body: `{
  "name": "Satya Nadella",
  "company": "Microsoft",
  "role": "CEO",
  "linkedin_url": "",
  "twitter_handle": "satya",
  "github_username": "",
  "context": "Looking for his AI strategy"
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
      description: "Start discovery for up to 20 people in one request. Each person gets its own job ID.",
      auth: false,
      body: `{
  "persons": [
    { "name": "Person A", "company": "Company A", "role": "CTO" },
    { "name": "Person B", "company": "Company B" }
  ]
}`,
      response: `{
  "jobs": [
    { "job_id": "uuid-1", "name": "Person A", "status": "running" },
    { "job_id": "uuid-2", "name": "Person B", "status": "running" }
  ],
  "total": 2
}`,
    },
    {
      method: "GET",
      path: "/api/jobs/{job_id}",
      description: "Poll job status. When status=completed, the full profile is embedded in the response.",
      auth: false,
      params: "job_id: UUID returned by /discover",
      response: `{
  "id": "abc-123-...",
  "status": "completed",
  "person_id": "person-uuid",
  "total_cost": 0.0023,
  "latency_ms": 12400,
  "sources_hit": 14,
  "cache_hits": 3,
  "profile": {
    "name": "Satya Nadella",
    "current_role": "Chairman and CEO",
    "company": "Microsoft",
    "bio": "...",
    "confidence_score": 0.92
  }
}`,
    },
  ],
  "Profile Retrieval": [
    {
      method: "GET",
      path: "/api/persons/{person_id}/summary",
      description: "Complete profile with all fields — no source list attached. Best for display cards, CRM sync, and quick lookups. Returns bio, expertise, key_facts, career_timeline, education, notable_work, social_links, confidence_score, and sources_count.",
      auth: true,
      params: "person_id: UUID",
      response: `{
  "id": "person-uuid",
  "name": "Sam Altman",
  "current_role": "CEO and Co-Founder",
  "company": "OpenAI",
  "location": "San Francisco, CA",
  "image_url": "https://...supabase.co/.../sam-altman.jpg",
  "bio": "Sam Altman is a prominent entrepreneur...",
  "expertise": ["Artificial Intelligence", "Machine Learning", "Startup Acceleration"],
  "key_facts": ["Co-founded OpenAI in 2015", "Previously president of Y Combinator"],
  "notable_work": ["Leading development of ChatGPT", "Driving GPT-4 advancements"],
  "education": ["Computer Science (incomplete), Stanford University"],
  "career_timeline": [
    { "type": "role", "title": "CEO", "company": "OpenAI", "start_date": "2015", "end_date": "Present" }
  ],
  "social_links": { "linkedin": "https://linkedin.com/in/sam-altman", "twitter": "https://x.com/sama" },
  "confidence_score": 0.808,
  "reputation_score": null,
  "sources_count": 67,
  "last_updated": "2026-03-14T10:58:34Z"
}`,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}/fields",
      description: "Request only the fields you need. Each field is returned with its value, a per-field confidence_score, and the top 5 sources that support it — ranked by platform affinity (e.g. LinkedIn first for current_role, Wikipedia for bio, Crunchbase for career_timeline). Ideal for CRM enrichment, data verification, and provenance-aware pipelines.",
      auth: true,
      params: "fields: comma-separated field names (default: name,current_role,company,image_url)\nAvailable: name, current_role, company, location, bio, image_url, education, key_facts, social_links, expertise, notable_work, career_timeline, confidence_score, reputation_score, status, version, created_at, updated_at",
      response: `{
  "id": "person-uuid",
  "person": { "name": "Sam Altman", "company": "OpenAI", "current_role": "CEO" },
  "overall_confidence": 0.808,
  "total_sources": 67,
  "fields": {
    "name": {
      "value": "Sam Altman",
      "confidence_score": 0.964,
      "sources": [
        {
          "platform": "crunchbase",
          "source_type": "crunchbase",
          "url": "https://crunchbase.com/person/sam-altman",
          "title": "Sam Altman - CEO & Co-Founder @ OpenAI",
          "confidence_score": 0.98,
          "relevance_score": 1.0,
          "source_reliability": 0.95,
          "scorer_reason": "Direct profile for the exact target person",
          "fetched_at": "2026-03-13T13:15:25Z"
        }
      ]
    },
    "current_role": {
      "value": "CEO and Co-Founder",
      "confidence_score": 0.96,
      "sources": [ "..." ]
    }
  }
}`,
    },
    {
      method: "GET",
      path: "/api/persons",
      description: "List all discovered persons with pagination and optional search.",
      auth: false,
      params: "page (int, default 1), per_page (int, default 20), search (string — name or company)",
      response: `{
  "items": [{ "id": "...", "name": "Sam Altman", "company": "OpenAI", "image_url": "..." }],
  "total": 14,
  "page": 1,
  "per_page": 20
}`,
    },
    {
      method: "GET",
      path: "/api/persons/semantic-search",
      description: "Vector-similarity search over all stored persons. Returns persons ranked by semantic closeness to the natural-language query. Useful for queries like 'logistics CTO in India' or 'AI researcher from IIT'.",
      auth: true,
      params: "q: search text (required), limit: max results (default 10)",
      response: `{
  "results": [
    {
      "id": "a1b2c3d4-...",
      "name": "Prashant Parashar",
      "company": "Delhivery",
      "current_role": "Senior Vice President & Head of Technology",
      "similarity_score": 0.91
    }
  ],
  "total": 1
}`,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}",
      description: "Full person profile with all raw sources, job history, and version log.",
      auth: false,
      params: "person_id: UUID",
    },
  ],
  "Person Actions": [
    {
      method: "PUT",
      path: "/api/persons/{person_id}",
      description: "Update any person field (admin only). Automatically creates a version snapshot for rollback.",
      auth: true,
      body: `{
  "name": "Updated Name",
  "current_role": "New Role",
  "company": "New Company",
  "bio": "Updated bio text...",
  "image_url": null
}`,
    },
    {
      method: "DELETE",
      path: "/api/persons/{person_id}",
      description: "Permanently delete a person and all their sources, jobs, notes, and tags (admin only).",
      auth: true,
    },
    {
      method: "POST",
      path: "/api/persons/{person_id}/re-search",
      description: "Re-run the full discovery pipeline using the person's current profile data as context (admin only). Returns a new job ID to poll.",
      auth: true,
      response: `{ "job_id": "new-uuid", "status": "running", "message": "Re-search started." }`,
    },
    {
      method: "POST",
      path: "/api/persons/{person_id}/refresh-image",
      description: "Clear the current profile photo and re-resolve it from scratch using the quality-first waterfall (LinkedIn CDN → Wikipedia → Knowledge Graph → Google Images). Rejects landscape/group photos automatically — only accepts portrait/square headshots. Takes 5–15 seconds.",
      auth: true,
      response: `{
  "person_id": "uuid",
  "name": "Sam Altman",
  "image_url": "https://...supabase.co/.../sam-altman-d032b9ad.jpg",
  "message": "Image refreshed successfully."
}`,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}/export",
      description: "Export the profile in one of four formats: JSON (full data), CSV (fields table), PDF (styled A4 report), or PPTX (3-slide deck).",
      auth: true,
      params: "format: json | csv | pdf | pptx (default: json)",
    },
  ],
  Authentication: [
    {
      method: "POST",
      path: "/api/auth/login",
      description: "Login with admin credentials. Returns a short-lived access token (30 min) and a refresh token (7 days).",
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
      description: "Exchange a refresh token for a new access token without re-entering credentials.",
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
      description: "Create a programmatic API key (admin only). The full key value is shown only once — store it immediately. Pass as X-API-Key header for 5× higher rate limits than JWT tokens.",
      auth: true,
      body: `{ "name": "My CRM Integration", "rate_limit_per_day": 500 }`,
      response: `{
  "id": "key-uuid",
  "name": "My CRM Integration",
  "key": "dk_live_...",
  "rate_limit_per_day": 500
}`,
    },
    {
      method: "GET",
      path: "/api/api-keys",
      description: "List all active API keys with usage statistics (admin only).",
      auth: true,
    },
    {
      method: "DELETE",
      path: "/api/api-keys/{key_id}",
      description: "Permanently revoke an API key (admin only). Takes effect immediately.",
      auth: true,
    },
  ],
  Webhooks: [
    {
      method: "POST",
      path: "/api/webhooks",
      description: "Register a webhook URL to receive real-time event notifications (admin only). Supports job.completed and person.updated events. Optionally include a signing secret for HMAC-SHA256 payload verification.",
      auth: true,
      body: `{
  "url": "https://your-server.com/webhook",
  "events": ["job.completed", "person.updated"],
  "secret": "optional-signing-secret"
}`,
      response: `{
  "id": "wh-uuid",
  "url": "https://your-server.com/webhook",
  "events": ["job.completed"],
  "active": true
}`,
    },
    {
      method: "GET",
      path: "/api/webhooks",
      description: "List all registered webhooks (admin only).",
      auth: true,
    },
    {
      method: "DELETE",
      path: "/api/webhooks/{webhook_id}",
      description: "Deactivate a webhook (admin only).",
      auth: true,
    },
    {
      method: "GET",
      path: "/api/webhooks/{webhook_id}/deliveries",
      description: "View last 50 delivery attempts with HTTP status, success flag, and retry count (admin only).",
      auth: true,
    },
  ],
  Intelligence: [
    {
      method: "GET",
      path: "/api/persons/{person_id}/sentiment",
      description: "On-demand sentiment analysis of the person's public perception across their stored sources. Uses OpenAI gpt-4.1-mini. Results are cached per-person.",
      auth: true,
      response: `{
  "overall_sentiment": "positive",
  "sentiment_score": 0.85,
  "public_perception": "Widely regarded as a strong technical leader...",
  "controversy_flags": [],
  "strengths_in_perception": ["Technical depth", "Visionary leadership"]
}`,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}/influence",
      description: "On-demand influence scoring across 6 dimensions: industry impact, thought leadership, network reach, innovation, media presence, community contribution.",
      auth: true,
      response: `{
  "overall_influence_score": 78,
  "dimensions": {
    "industry_impact": { "score": 80, "reasoning": "..." },
    "thought_leadership": { "score": 75, "reasoning": "..." }
  },
  "key_influence_areas": ["Logistics tech", "Engineering leadership"]
}`,
    },
    {
      method: "POST",
      path: "/api/persons/relationships",
      description: "Map professional relationship between two discovered persons.",
      auth: true,
      body: `{ "person_a_id": "uuid-A", "person_b_id": "uuid-B" }`,
      response: `{
  "relationship_type": "professional",
  "connection_strength": "moderate",
  "shared_contexts": ["Indian startup ecosystem"],
  "relationship_summary": "Both are senior technology leaders..."
}`,
    },
    {
      method: "POST",
      path: "/api/persons/{person_id}/meeting-prep",
      description: "Generate a meeting preparation brief: talking points, shared interests, potential risks, and suggested questions.",
      auth: true,
    },
    {
      method: "GET",
      path: "/api/persons/{person_id}/verify",
      description: "Cross-verify key profile facts (role, company, location) against live sources. Returns verification status per fact.",
      auth: true,
    },
  ],
  Admin: [
    {
      method: "GET",
      path: "/api/admin/costs",
      description: "LLM cost dashboard: total spend, average cost per discovery, per-model breakdown, and recent job costs.",
      auth: true,
    },
    {
      method: "GET",
      path: "/api/admin/rate-limits",
      description: "Current rate limit status per data source (Tavily, Apify, SerpAPI, etc.).",
      auth: true,
    },
    {
      method: "POST",
      path: "/api/admin/users",
      description: "Create a new admin user (admin only). Roles: admin, viewer.",
      auth: true,
      body: `{ "email": "analyst@company.com", "password": "secure123!", "role": "viewer" }`,
      response: `{ "id": "user-uuid", "email": "analyst@company.com", "role": "viewer", "created_at": "..." }`,
    },
    {
      method: "GET",
      path: "/api/admin/users",
      description: "List all admin users (admin only).",
      auth: true,
      response: `[{ "id": "user-uuid", "email": "admin@discovery.local", "role": "admin" }]`,
    },
    {
      method: "DELETE",
      path: "/api/admin/users/{user_id}",
      description: "Delete an admin user (admin only). Cannot delete yourself.",
      auth: true,
      response: `{ "deleted": true }`,
    },
    {
      method: "POST",
      path: "/api/cache/cleanup",
      description: "Remove expired cache entries to free memory (admin only).",
      auth: true,
      response: `{ "cleaned": 47 }`,
    },
    {
      method: "GET",
      path: "/api/health",
      description: "Health check — returns system status, database connectivity, and version. No auth required.",
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

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 space-y-4">
        <div>
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">Base URL</h2>
          <code className="text-lg text-blue-400 font-mono">{API_BASE}</code>
        </div>
        <p className="text-sm text-gray-400">
          All endpoints return JSON. Authentication uses JWT Bearer tokens — obtain one via <code className="text-gray-300">POST /api/auth/login</code>.
          Only <code className="text-gray-300">GET /api/health</code> and <code className="text-gray-300">POST /api/auth/login</code> are public; all other endpoints require a Bearer token.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
          <div className="rounded-lg bg-white/[0.03] border border-white/10 p-3">
            <p className="text-xs text-gray-500 mb-1">Key endpoints</p>
            <p className="text-sm text-white font-medium">
              <span className="text-emerald-400">GET</span> /summary · <span className="text-emerald-400">GET</span> /fields
            </p>
            <p className="text-xs text-gray-500 mt-1">Full profile or selective fields with per-source provenance</p>
          </div>
          <div className="rounded-lg bg-white/[0.03] border border-white/10 p-3">
            <p className="text-xs text-gray-500 mb-1">Image pipeline</p>
            <p className="text-sm text-white font-medium">
              <span className="text-blue-400">POST</span> /refresh-image
            </p>
            <p className="text-xs text-gray-500 mt-1">Force re-resolve photo from LinkedIn → Wikipedia → Knowledge Graph</p>
          </div>
          <div className="rounded-lg bg-white/[0.03] border border-white/10 p-3">
            <p className="text-xs text-gray-500 mb-1">LLM stack</p>
            <p className="text-sm text-white font-medium">Groq + OpenAI</p>
            <p className="text-xs text-gray-500 mt-1">llama-3.1-8b · llama-4-scout · gpt-4.1-mini</p>
          </div>
        </div>
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

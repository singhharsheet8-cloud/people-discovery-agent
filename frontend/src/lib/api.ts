import type {
  DiscoverRequest,
  JobSummary,
  PersonProfile,
  PersonSummary,
  CostStats,
  SavedList,
  PersonNote,
  PersonTagItem,
  AuditEntry,
  UsageAnalytics,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}

function storeTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("admin_token");
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    storeTokens(data.access_token, data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

async function fetchApi<T>(path: string, options?: RequestInit, isRetry = false): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url, {
    ...options,
    headers,
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && window.location.pathname.startsWith("/admin")) {
      if (!isRetry) {
        const refreshed = await tryRefreshToken();
        if (refreshed) return fetchApi<T>(path, options, true);
      }
      clearTokens();
      window.location.href = "/login?expired=1";
      throw new Error("Session expired");
    }
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const message = error?.message || error?.detail || res.statusText;
    throw new Error(typeof message === "string" ? message : `API error: ${res.status}`);
  }
  return res.json();
}

export async function discoverPerson(data: DiscoverRequest) {
  return fetchApi<{ job_id: string; status: string; message: string }>("/discover", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function batchDiscover(persons: DiscoverRequest[]) {
  return fetchApi<{ jobs: { job_id: string; name: string; status: string }[]; total: number }>(
    "/discover/batch",
    { method: "POST", body: JSON.stringify({ persons }) }
  );
}

export async function getJob(jobId: string) {
  return fetchApi<JobSummary>(`/jobs/${jobId}`);
}

export async function getPersons(page = 1, perPage = 20, search = "") {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  if (search) params.set("search", search);
  return fetchApi<{
    items: PersonSummary[];
    total: number;
    page: number;
    per_page: number;
  }>(`/persons?${params}`);
}

export async function getPerson(id: string) {
  return fetchApi<PersonProfile>(`/persons/${id}`);
}

export async function suggestPersons(query: string, limit: number = 10) {
  return fetchApi<PersonSummary[]>(`/suggest?q=${encodeURIComponent(query)}&limit=${limit}`);
}

export async function updatePerson(id: string, data: Partial<PersonProfile>) {
  return fetchApi<PersonProfile>(`/persons/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePerson(id: string) {
  return fetchApi<{ deleted: boolean }>(`/persons/${id}`, { method: "DELETE" });
}

export async function reSearchPerson(id: string) {
  return fetchApi<{ job_id: string; status: string }>(`/persons/${id}/re-search`, {
    method: "POST",
  });
}

export async function getCostStats() {
  return fetchApi<CostStats>("/admin/costs");
}

export async function loginAdmin(email: string, password: string) {
  const data = await fetchApi<{
    access_token: string;
    refresh_token: string;
    expires_in: number;
    token_type: string;
    email: string;
    role: string;
  }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  storeTokens(data.access_token, data.refresh_token);
  return data;
}

export async function exportPerson(id: string, format: "json" | "csv" | "pdf" | "pptx" = "json") {
  const url = `${API_BASE}/persons/${id}/export?format=${format}`;
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  if (format === "pdf" || format === "pptx") return res.blob();
  if (format === "csv") return res.text();
  return res.json();
}

export async function healthCheck() {
  return fetchApi<Record<string, unknown>>("/health");
}

// ── API Keys ──────────────────────────────────────────────────────

export interface ApiKeyItem {
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

export async function getApiKeys() {
  return fetchApi<ApiKeyItem[]>("/api-keys");
}

export async function createApiKey(name: string, rateLimitPerDay: number) {
  return fetchApi<ApiKeyItem>("/api-keys", {
    method: "POST",
    body: JSON.stringify({ name, rate_limit_per_day: rateLimitPerDay }),
  });
}

export async function revokeApiKey(id: string) {
  return fetchApi<{ revoked: boolean }>(`/api-keys/${id}`, { method: "DELETE" });
}

// ── Webhooks ──────────────────────────────────────────────────────

export interface WebhookItem {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  created_at: string;
}

export interface WebhookDelivery {
  id: string;
  event: string;
  status_code: number | null;
  success: boolean;
  attempts: number;
  created_at: string;
}

export async function getWebhooks() {
  return fetchApi<WebhookItem[]>("/webhooks");
}

export async function createWebhook(url: string, events: string[]) {
  return fetchApi<WebhookItem>("/webhooks", {
    method: "POST",
    body: JSON.stringify({ url, events }),
  });
}

export async function deleteWebhook(id: string) {
  return fetchApi<{ deleted: boolean }>(`/webhooks/${id}`, { method: "DELETE" });
}

export async function getWebhookDeliveries(id: string) {
  return fetchApi<WebhookDelivery[]>(`/webhooks/${id}/deliveries`);
}

// --- Intelligence APIs ---

export async function getSentimentAnalysis(personId: string) {
  return fetchApi<Record<string, unknown>>(`/persons/${personId}/sentiment`);
}

export async function getInfluenceScore(personId: string) {
  return fetchApi<Record<string, unknown>>(`/persons/${personId}/influence`);
}

export async function getRelationshipMap(personAId: string, personBId: string) {
  return fetchApi<Record<string, unknown>>("/persons/relationships", {
    method: "POST",
    body: JSON.stringify({ person_a_id: personAId, person_b_id: personBId }),
  });
}

export async function getMeetingPrep(personId: string, context?: string) {
  return fetchApi<Record<string, unknown>>(`/persons/${personId}/meeting-prep`, {
    method: "POST",
    body: JSON.stringify({ context: context || "" }),
  });
}

export async function getFactVerification(personId: string) {
  return fetchApi<Record<string, unknown>>(`/persons/${personId}/verify`);
}

// --- Saved Lists ---
export async function getLists() {
  return fetchApi<SavedList[]>("/lists");
}

export async function createList(data: { name: string; description?: string; color?: string }) {
  return fetchApi<SavedList>("/lists", { method: "POST", body: JSON.stringify(data) });
}

export async function updateList(id: string, data: { name?: string; description?: string; color?: string }) {
  return fetchApi<SavedList>(`/lists/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteList(id: string) {
  return fetchApi<{ deleted: boolean }>(`/lists/${id}`, { method: "DELETE" });
}

export async function getListPersons(listId: string, page = 1, perPage = 20) {
  return fetchApi<{ items: PersonSummary[]; total: number }>(`/lists/${listId}/persons?page=${page}&per_page=${perPage}`);
}

export async function addToList(listId: string, personIds: string[]) {
  return fetchApi<{ added: number }>(`/lists/${listId}/persons`, { method: "POST", body: JSON.stringify({ person_ids: personIds }) });
}

export async function removeFromList(listId: string, personId: string) {
  return fetchApi<{ removed: boolean }>(`/lists/${listId}/persons/${personId}`, { method: "DELETE" });
}

// --- Notes ---
export async function getNotes(personId: string) {
  return fetchApi<PersonNote[]>(`/persons/${personId}/notes`);
}

export async function addNote(personId: string, content: string) {
  return fetchApi<PersonNote>(`/persons/${personId}/notes`, { method: "POST", body: JSON.stringify({ content }) });
}

export async function updateNote(noteId: string, content: string) {
  return fetchApi<PersonNote>(`/notes/${noteId}`, { method: "PUT", body: JSON.stringify({ content }) });
}

export async function deleteNote(noteId: string) {
  return fetchApi<{ deleted: boolean }>(`/notes/${noteId}`, { method: "DELETE" });
}

// --- Tags ---
export async function getTags(personId: string) {
  return fetchApi<PersonTagItem[]>(`/persons/${personId}/tags`);
}

export async function addTags(personId: string, tags: string[]) {
  return fetchApi<{ added: number }>(`/persons/${personId}/tags`, { method: "POST", body: JSON.stringify({ tags }) });
}

export async function removeTag(personId: string, tag: string) {
  return fetchApi<{ removed: boolean }>(`/persons/${personId}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" });
}

export async function getAllTags() {
  return fetchApi<Array<{ tag: string; count: number }>>("/tags");
}

// --- Public Shares ---
export async function createShare(personId: string) {
  return fetchApi<{ share_token: string; share_url: string }>(`/persons/${personId}/share`, { method: "POST" });
}

export async function deleteShare(personId: string) {
  return fetchApi<{ revoked: boolean }>(`/persons/${personId}/share`, { method: "DELETE" });
}

// --- Audit ---
export async function getAuditLog(page = 1, perPage = 50, action?: string) {
  const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
  if (action) params.set("action", action);
  return fetchApi<{ items: AuditEntry[]; total: number }>(`/admin/audit?${params}`);
}

// --- Analytics ---
export async function getUsageAnalytics() {
  return fetchApi<UsageAnalytics>("/admin/analytics");
}

// --- Advanced Persons Listing ---
export async function getPersonsFiltered(params: {
  page?: number;
  per_page?: number;
  search?: string;
  company?: string;
  location?: string;
  min_confidence?: number;
  sort_by?: string;
  sort_order?: string;
}) {
  const p = new URLSearchParams();
  if (params.page) p.set("page", String(params.page));
  if (params.per_page) p.set("per_page", String(params.per_page));
  if (params.search) p.set("search", params.search);
  if (params.company) p.set("company", params.company);
  if (params.location) p.set("location", params.location);
  if (params.min_confidence !== undefined) p.set("min_confidence", String(params.min_confidence));
  if (params.sort_by) p.set("sort_by", params.sort_by);
  if (params.sort_order) p.set("sort_order", params.sort_order);
  return fetchApi<{ items: PersonSummary[]; total: number; page: number; per_page: number }>(`/persons?${p}`);
}

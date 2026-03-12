import type {
  DiscoverRequest,
  JobSummary,
  PersonProfile,
  PersonSummary,
  CostStats,
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

export async function batchDiscover(persons: DiscoverRequest[]) {
  return fetchApi<{ jobs: { job_id: string; name: string; status: string }[]; total: number }>(
    "/discover/batch",
    { method: "POST", body: JSON.stringify({ persons }) }
  );
}

export async function exportPerson(id: string, format: "json" | "csv" | "pdf" = "json") {
  const url = `${API_BASE}/persons/${id}/export?format=${format}`;
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
  if (format === "pdf") return res.blob();
  if (format === "csv") return res.text();
  return res.json();
}

export async function healthCheck() {
  return fetchApi<Record<string, unknown>>("/health");
}

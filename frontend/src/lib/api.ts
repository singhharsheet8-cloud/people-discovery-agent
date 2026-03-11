import type {
  DiscoverRequest,
  JobSummary,
  PersonProfile,
  PersonSummary,
  CostStats,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("admin_token");
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
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
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = typeof error === "object" && error !== null && "detail" in error
      ? (error as { detail?: string }).detail
      : res.statusText;
    throw new Error(typeof detail === "string" ? detail : `API error: ${res.status}`);
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
  return fetchApi<{ token: string; email: string; role: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function healthCheck() {
  return fetchApi<Record<string, unknown>>("/health");
}

export interface DiscoverRequest {
  name: string;
  company: string;
  role: string;
  location: string;
  linkedin_url: string;
  twitter_handle: string;
  github_username: string;
  instagram_handle: string;
  context: string;
}

export interface PersonSource {
  id?: string;
  source_type?: string;
  platform: string;
  url: string;
  title: string;
  raw_content?: string | null;
  snippet?: string;
  structured_data?: Record<string, unknown> | null;
  confidence?: number;
  relevance_score: number;
  source_reliability?: number;
  fetched_at?: string;
}

export interface PersonProfile {
  id: string;
  name: string;
  current_role?: string;
  company?: string;
  location?: string;
  bio?: string;
  education?: string[];
  key_facts?: string[];
  social_links?: Record<string, string>;
  expertise?: string[];
  notable_work?: string[];
  career_timeline?: Array<Record<string, unknown>>;
  confidence_score: number;
  reputation_score?: number;
  status: string;
  version: number;
  sources: PersonSource[];
  jobs: JobSummary[];
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  id: string;
  person_id?: string;
  status: string;
  input_params?: Record<string, unknown>;
  cost_breakdown?: Record<string, unknown>;
  total_cost: number;
  latency_ms?: number;
  sources_hit: number;
  cache_hits: number;
  error_message?: string;
  created_at: string;
  completed_at?: string;
  profile?: PersonProfile;
}

export interface PersonSummary {
  id: string;
  name: string;
  company?: string;
  current_role?: string;
  confidence_score: number;
  status: string;
  sources_count: number;
  created_at: string;
  updated_at: string;
}

export interface CostStats {
  total_spend: number;
  total_jobs: number;
  average_cost: number;
  recent_jobs: Array<{
    id: string;
    total_cost: number;
    latency_ms: number | null;
    sources_hit: number;
    cache_hits: number;
    created_at: string;
  }>;
}

export type WSMessageType =
  | "connected"
  | "status"
  | "clarification"
  | "result"
  | "error";

export interface WSMessage {
  type: WSMessageType;
  session_id?: string;
  step?: string;
  message?: string;
  question?: string;
  suggestions?: string[];
  reason?: string;
  profile?: Partial<PersonProfile>;
  confidence?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  timestamp: Date;
  data?: {
    type: "status" | "clarification" | "result";
    profile?: PersonProfile;
    confidence?: number;
    suggestions?: string[];
  };
}

export interface SavedList {
  id: string;
  name: string;
  description?: string;
  color: string;
  person_count: number;
  created_at: string;
  updated_at: string;
}

export interface PersonNote {
  id: string;
  person_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface PersonTagItem {
  tag: string;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  user_email: string;
  action: string;
  target_type: string;
  target_id?: string;
  details?: string;
  ip_address?: string;
  created_at: string;
}

export interface UsageAnalytics {
  total_persons: number;
  total_sources: number;
  total_discoveries: number;
  discoveries_last_7_days: Array<{ date: string; count: number }>;
  discoveries_last_30_days: Array<{ date: string; count: number }>;
  top_searched_companies: Array<{ company: string; count: number }>;
  source_distribution: Array<{ platform: string; count: number }>;
  avg_confidence_score: number;
  discoveries_by_status: Array<{ status: string; count: number }>;
}

export interface PersonSource {
  title: string;
  url: string;
  platform: string;
  snippet: string;
  relevance_score: number;
}

export interface PersonProfile {
  name: string;
  confidence_score: number;
  current_role?: string;
  company?: string;
  location?: string;
  bio?: string;
  linkedin_url?: string;
  key_facts: string[];
  education: string[];
  expertise: string[];
  notable_work: string[];
  social_links: Record<string, string>;
  sources: PersonSource[];
}

export interface ClarificationData {
  question: string;
  suggestions: string[];
  reason: string;
}

export type WSMessageType = "connected" | "status" | "clarification" | "result" | "error";

export interface WSMessage {
  type: WSMessageType;
  session_id?: string;
  step?: string;
  message?: string;
  question?: string;
  suggestions?: string[];
  reason?: string;
  profile?: PersonProfile;
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

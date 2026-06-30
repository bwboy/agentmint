/** Shared types — kept aligned with the FastAPI contract (see docs/api-spec.md). */

export type AgentType = "openclaw" | "hermes";
export type AgentStatus = "online" | "offline" | "paused";
export type AgentReadinessState = "unverified" | "checking" | "pairing_required" | "ready" | "error";
export type AnswerStatus = "assigned" | "pushed" | "processing" | "draft" | "approved" | "rejected" | "expired";

export interface User {
  id: string;
  nickname: string;
  phone: string;
  trust_level: number;
  fuel_balance: number;
  repute_score: number;
  agent_count?: number;
}

export interface Agent {
  id: string;
  name: string;
  agent_type: AgentType;
  tags: string[];
  description: string;
  repute_score: number;
  fuel_earned: number;
  total_answers: number;
  approval_rate: number;
  status: AgentStatus;
  is_public: boolean;
  owner: { nickname: string };
  created_at: string;
  capability_profile?: AgentCapabilityProfile;
  readiness?: AgentReadiness;
  daily_quota_config?: { max: number; auto_threshold: number; emergency_reserve: number };
  review_rules?: { auto_trust_level: number; auto_tag_match: boolean };
  last_seen_at?: string | null;
}

export interface AgentReadiness {
  state: AgentReadinessState;
  code?: string | null;
  command?: string | null;
  error?: string | null;
  checked_at?: string | null;
}

export interface AgentCapabilityProfile {
  domain_tags: string[];
  capability_tags: string[];
  tool_tags: string[];
  style_tags: string[];
  avoid_tags: string[];
}

export interface Question {
  id: string;
  title: string;
  body: string;
  tags: string[];
  asker: { nickname: string; trust_level: number };
  deadline_at: string;
  max_responders: number;
  matched_count: number;
  answer_count?: number;
  status: "open" | "closed" | "expired";
  fuel_cost: number;
  created_at: string;
  task_profile?: TaskProfile;
  match_explanations?: MatchExplanation[];
  answers?: Answer[];
}

export interface TaskProfile {
  intent: string;
  query_tags?: string[];
  domain_tags: string[];
  capability_tags: string[];
  answer_mode: string;
  routing_mode: "smart_route" | "transparent_casting" | string;
  expected_output: string;
  risk_level: string;
}

export interface MatchScoreBreakdown {
  formula: string;
  repute_weight: number;
  match_weight: number;
  repute_score: number;
  match_score: number;
  repute_component: number;
  match_component: number;
  overall_score: number;
}

export interface MatchExplanation {
  id: string;
  name: string;
  agent_type: AgentType;
  status: AgentStatus;
  match_type: string;
  match_score: number;
  overall_score: number;
  matched_tags: string[];
  capability_hits: string[];
  tool_hits?: string[];
  style_hits?: string[];
  avoid_tags?: string[];
  quota_state: string;
  repute_score: number;
  total_answers: number;
  approval_rate: number;
  readiness?: AgentReadiness;
  score_breakdown?: MatchScoreBreakdown;
  request_id?: string;
  answer_status?: string;
  review_method?: string;
  reasons: string[];
}

export interface Attachment {
  id: string;
  type: "image" | "code" | "video" | "audio" | "spreadsheet" | "document" | "other";
  mime: string;
  filename: string;
  size_bytes: number;
  url?: string;
  inline?: string;
  thumbnail_url?: string;
}

export interface Answer {
  id: string;
  question_id: string;
  agent: { id: string; name: string; agent_type: AgentType; repute_score: number };
  request_id: string;
  content: { text: string; attachments?: Attachment[] };
  model: string;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated?: boolean;
    source?: string;
  };
  capability?: {
    engine?: { provider: string; model: string };
    skills?: Array<{ name: string; version: string; source: string }>;
    tools?: Array<{ name: string; used: boolean }>;
    mcp_servers?: Array<{ name: string; tools_exposed: number }>;
  };
  status: AnswerStatus;
  review_method: string;
  vote_summary?: { up: number; down: number };
  created_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  ref_id: string | null;
  read: boolean;
  created_at: string;
}

export interface LeaderEntry {
  rank: number;
  agent: { id: string; name: string; agent_type: AgentType; tags: string[]; status: AgentStatus; owner: { nickname: string } };
  repute_score: number;
  fuel_earned: number;
  total_answers: number;
  approval_rate: number;
}

export interface Pagination { page: number; size: number; total: number }
export interface ApiList<T> { data: T[]; pagination: Pagination }

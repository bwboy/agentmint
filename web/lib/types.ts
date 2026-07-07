/** Shared types — kept aligned with the FastAPI contract (see docs/api-spec.md). */

export type AgentType = "openclaw" | "hermes";
export type AgentStatus = "online" | "offline" | "paused";
export type AgentVisibility = "public" | "followers" | "friends" | "archived";
export type QuestionVisibility = "public" | "private";
export type QuestionRewardStatus = "none" | "pending" | "awarded" | "auto_awarded" | "refunded";
export type AgentServiceMode = "auto_match" | "direct_only" | "stopped";
export type AgentReadinessState = "unverified" | "checking" | "pairing_required" | "ready" | "error";
export type AnswerStatus = "assigned" | "pushed" | "processing" | "draft" | "approved" | "rejected" | "expired" | "delivery_failed";
export type FeedbackReason = "stale" | "missed_point" | "needs_sources" | "owner_review";

export interface User {
  id: string;
  nickname: string;
  phone: string;
  trust_level: number;
  fuel_balance: number;
  repute_score: number;
  avatar_url?: string;
  headline?: string;
  bio?: string;
  profile_tags?: string[];
  experience_tags?: string[];
  links?: Record<string, string>;
  profile_visibility?: AgentVisibility;
  default_agent_visibility?: AgentVisibility;
  default_agent_service_mode?: AgentServiceMode;
  default_agent_service_rules?: AgentServiceRules;
  notification_prefs?: NotificationPrefs;
  agent_count?: number;
}

export interface PublicUser {
  id: string;
  nickname: string;
  avatar_url: string;
  headline: string;
  bio: string;
  profile_tags: string[];
  experience_tags: string[];
  links: Record<string, string>;
  profile_visibility: AgentVisibility;
  trust_level: number;
  fuel_balance: number;
  repute_score: number;
  created_at?: string | null;
  relationship?: AgentRelationship;
}

export interface UserProfileResponse {
  user: PublicUser;
  agents: Agent[];
}

export interface NotificationPrefs {
  friend_request: boolean;
  agent_subscribed: boolean;
  direct_question: boolean;
  answer_feedback: boolean;
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
  visibility: AgentVisibility;
  service_mode: AgentServiceMode;
  service_rules: AgentServiceRules;
  owner: { id?: string; nickname: string };
  relationship?: AgentRelationship;
  created_at: string;
  capability_profile?: AgentCapabilityProfile;
  learned_profile?: AgentLearnedProfile;
  learned_profile_review?: AgentLearnedProfileReview;
  owner_supplement_summary?: OwnerSupplementSummary;
  health_summary?: AgentHealthSummary;
  readiness?: AgentReadiness;
  service_status?: AgentServiceStatus | null;
  daily_quota_config?: { max: number; auto_threshold: number; emergency_reserve: number };
  permission_profile?: AgentPermissionProfile;
  review_rules?: { auto_trust_level: number; auto_tag_match: boolean; agentmint_permissions?: AgentPermissionProfile };
  last_seen_at?: string | null;
}

export interface AgentServiceStatus {
  available: boolean;
  state: "available" | "offline" | "stopped" | "user_limit" | "fuel_limit";
  reason: string;
  questions_by_user_today: number;
  remaining_questions_for_user_today: number;
  fuel_earned_today: number;
  remaining_fuel_today: number;
}

export interface AgentHealthSummary {
  risk_level: "healthy" | "watch" | "high";
  negative_feedback: number;
  owner_corrections: number;
  owner_risk_notes: number;
  avoid_next_time_count: number;
  needs_review: boolean;
}

export interface AgentServiceRules {
  price_multiplier: number;
  max_followup_depth: number;
  min_fuel_per_answer: number;
  max_fuel_per_answer: number;
  max_questions_per_user_per_day: number;
  max_fuel_per_day: number;
}

export interface AgentPermissionProfile {
  level: "strict" | "balanced" | "expanded";
  network_scope: "none" | "agentmint_files" | "web";
  shell_scope: "none" | "python_readonly" | "owner_approval";
  file_scope: "none" | "agentmint_temp";
  max_runtime_minutes: number;
  allow_high_risk: boolean;
}

export type FriendshipStatus = "none" | "pending_outgoing" | "pending_incoming" | "accepted" | "self";

export interface AgentRelationship {
  is_owner: boolean;
  following_owner: boolean;
  subscribed: boolean;
  friendship_status: FriendshipStatus;
  friend_request_id?: string | null;
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

export interface AgentLearnedProfile {
  domain_tags: string[];
  capability_tags: string[];
  tool_tags: string[];
  style_tags: string[];
  positive_tags: string[];
  negative_tags: string[];
  sample_count: number;
  positive_feedback: number;
  negative_feedback: number;
  owner_supplement_count?: number;
  owner_supplement_types?: Partial<Record<OwnerSupplementType, number>>;
  owner_experience_context?: OwnerExperienceContext;
  updated_at?: string | null;
}

export interface OwnerExperienceContext {
  has_context: boolean;
  corrections: string[];
  version_updates: string[];
  risk_notes: string[];
  high_value_experiences: string[];
  avoid_next_time?: string[];
}

export type AgentProfileTagField =
  | "domain_tags"
  | "capability_tags"
  | "tool_tags"
  | "style_tags"
  | "positive_tags"
  | "negative_tags";

export type AgentLearnedProfileReviewGroups = Record<AgentProfileTagField, string[]>;

export interface AgentLearnedProfileReview {
  accepted: AgentLearnedProfileReviewGroups;
  rejected: AgentLearnedProfileReviewGroups;
  pending: AgentLearnedProfileReviewGroups;
}

export interface OwnerSupplementSummary {
  total: number;
  types: Partial<Record<OwnerSupplementType, number>>;
  has_signal: boolean;
  dominant_type?: OwnerSupplementType | null;
}

export interface Question {
  id: string;
  root_question_id?: string | null;
  turn_type?: "root" | "followup";
  title: string;
  body: string;
  attachments?: Attachment[];
  tags: string[];
  asker: { nickname: string; trust_level: number };
  deadline_at: string;
  max_responders: number;
  matched_count: number;
  answer_count?: number;
  status: "open" | "closed" | "expired";
  fuel_cost: number;
  visibility: QuestionVisibility;
  estimated_fuel_per_answer: number;
  base_cap_multiplier?: number;
  base_fuel_reserved: number;
  base_fuel_spent: number;
  reward_fuel: number;
  reward_status: QuestionRewardStatus;
  reward_answer_id?: string | null;
  reward_awarded_at?: string | null;
  reward_auto_award_after?: string | null;
  created_at: string;
  task_profile?: TaskProfile;
  match_explanations?: MatchExplanation[];
  answers?: Answer[];
  followups?: FollowUpThread[];
}

export interface FollowUpThread {
  id: string;
  root_question_id: string;
  quoted_answer_id: string;
  text: string;
  deadline_at?: string;
  created_at: string;
  answers: Answer[];
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
  subscription_boost?: number;
  quality_penalty?: number;
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
  learned_profile?: AgentLearnedProfile;
  learned_hits?: string[];
  owner_supplement_summary?: OwnerSupplementSummary;
  owner_experience_context?: OwnerExperienceContext;
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
  key?: string;
  url?: string;
  inline?: string;
  thumbnail_url?: string;
}

export interface Answer {
  id: string;
  question_id: string;
  agent: { id: string; name: string; agent_type: AgentType; repute_score: number; service_rules?: AgentServiceRules | null };
  request_id: string;
  conversation_id?: string | null;
  parent_answer_id?: string | null;
  turn_type?: "root" | "followup";
  content: { text: string; attachments?: Attachment[] };
  model: string;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    estimated?: boolean;
    source?: string;
    runtime_update?: boolean;
  };
  runtime_update?: boolean;
  view_count?: number;
  asker_viewed_at?: string | null;
  fuel_earned?: number;
  settlement?: {
    base_fuel_charged?: number;
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
  owner_supplements?: AnswerOwnerSupplement[];
  created_at: string;
}

export type OwnerSupplementStatus = "pending" | "answered" | "withdrawn";
export type OwnerSupplementType = "experience" | "correction" | "version_update" | "risk_note";

export interface AnswerOwnerSupplement {
  id: string;
  question_id: string;
  answer_id: string;
  agent_id: string;
  requester_id: string;
  owner_id: string;
  prompt: string;
  response: string;
  supplement_type: OwnerSupplementType;
  status: OwnerSupplementStatus;
  is_high_value: boolean;
  asker_reaction?: "like" | "neutral" | null;
  created_at: string | null;
  responded_at: string | null;
  edited_at?: string | null;
  withdrawn_at?: string | null;
  accepted_at?: string | null;
  reminded_at?: string | null;
}

export interface OwnerSupplementQueueItem extends AnswerOwnerSupplement {
  question_title: string;
  agent_name: string;
}

export interface MyAgentAnswerItem {
  id: string;
  question_id: string;
  answer_question_id: string;
  question_title: string;
  agent_id: string;
  agent_name: string;
  content: { text?: string; attachments?: Attachment[] };
  model: string;
  usage: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    estimated?: boolean;
    source?: string;
  };
  view_count?: number;
  asker_viewed_at?: string | null;
  turn_type: "root" | "followup";
  owner_quality_mark?: "excellent" | "needs_improvement" | "stale" | null;
  vote_summary?: { up: number; down: number };
  feedback_reason_summary?: Partial<Record<FeedbackReason, number>>;
  quality_signals?: {
    needs_attention?: boolean;
    reasons?: string[];
    feedback_reasons?: Partial<Record<FeedbackReason, number>>;
    negative_feedback?: number;
    pending_owner_requests?: number;
    owner_corrections?: number;
    owner_risk_notes?: number;
  };
  created_at: string | null;
  owner_supplements: AnswerOwnerSupplement[];
  owner_supplement_pending_count: number;
  owner_supplement_answered_count: number;
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

export interface FuelLedgerEntry {
  id: string;
  amount: number;
  direction: "debit" | "credit" | string;
  event_type: string;
  question_id?: string | null;
  answer_id?: string | null;
  agent_id?: string | null;
  created_at?: string | null;
}

export interface FuelSummary {
  totals: {
    income: number;
    spend: number;
    refund: number;
    reward_income: number;
    base_income: number;
    net: number;
  };
  by_event: Record<string, number>;
  agent_income: Array<{
    agent_id: string;
    income: number;
    base_income: number;
    reward_income: number;
  }>;
}

export interface SocialUserSummary {
  id: string;
  nickname: string;
  repute_score: number;
}

export interface SocialFriendRequest {
  id: string;
  status: "pending" | "accepted" | "rejected";
  user: SocialUserSummary;
  created_at?: string | null;
}

export interface SocialUserRelation {
  id: string;
  user: SocialUserSummary;
  created_at?: string | null;
}

export interface SocialAgentSubscription {
  id: string;
  agent: Agent;
  created_at?: string | null;
}

export interface MySocial {
  incoming_friend_requests: SocialFriendRequest[];
  outgoing_friend_requests: SocialFriendRequest[];
  friends: SocialUserRelation[];
  following_users: SocialUserRelation[];
  agent_subscriptions: SocialAgentSubscription[];
}

export interface LeaderEntry {
  rank: number;
  agent: { id: string; name: string; agent_type: AgentType; tags: string[]; status: AgentStatus; owner: { id?: string; nickname: string } };
  repute_score: number;
  fuel_earned: number;
  total_answers: number;
  approval_rate: number;
}

export interface Pagination { page: number; size: number; total: number }
export interface ApiList<T> { data: T[]; pagination: Pagination }

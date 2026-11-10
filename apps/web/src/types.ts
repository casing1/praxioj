export interface Criterion {
  id: string;
  title: string;
  description: string;
  max_score: number;
}

export interface ResourceLimits {
  max_messages: number;
  max_message_chars: number;
  max_submission_chars: number;
  max_model_calls?: number;
  max_tool_calls?: number;
  max_total_tokens?: number | null;
  request_timeout_seconds?: number;
  max_run_seconds?: number;
  max_file_bytes?: number;
  max_workspace_bytes?: number;
  max_workspace_files?: number;
}

export interface ProviderCapabilities {
  tools: boolean;
  system_messages: boolean;
  temperature: boolean;
  token_limit_parameter: "max_tokens" | "max_completion_tokens";
}

export interface RuntimeOptions {
  default_profile: string;
  profiles: {
    id: string;
    label: string;
    model: string;
    capabilities: ProviderCapabilities;
  }[];
}

export interface Problem {
  id: string;
  version: string;
  title: string;
  description: string;
  category: string;
  difficulty: string;
  initial_resources: { name: string; content: string; media_type: string }[];
  allowed_ai_capabilities: string[];
  allowed_tools: string[];
  tool_permissions?: string[];
  ai_policy?: { allowed_providers: string[]; allowed_models: string[]; max_output_tokens: number; allow_temperature: boolean };
  resource_limits: ResourceLimits;
  submission: { kind: "text"; instructions: string };
  evaluation: {
    evaluator_id: string;
    evaluator_version: string;
    criteria: Criterion[];
  };
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  created_at: string;
  tool_calls?: { id: string; name: string; arguments: Record<string, unknown> }[];
  tool_call_id?: string | null;
}

export interface Run {
  id: string;
  session_id: string;
  request_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  error: { code: string; message: string } | null;
  created_at: string;
  finished_at: string | null;
  job?: { state: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED"; attempt: number; recovery_reason: string | null; external_effect_uncertain: boolean } | null;
}

export interface SessionUsage {
  model_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  usage_complete: boolean;
  estimated: boolean;
  cost_estimate: number | null;
  currency: string | null;
  cost_estimate_complete: boolean;
  limits: ResourceLimits;
}

export interface WorkspaceFile {
  path: string;
  content: string;
  sha256: string;
  byte_size: number;
  revision: number;
}

export interface SolveSession {
  id: string;
  problem_id: string;
  problem_version: string;
  status: "active" | "submitted" | "ended";
  messages: ConversationMessage[];
  submission_id: string | null;
  evaluation_id: string | null;
  created_at: string;
  runtime_profile: string;
  model_configuration: { provider: string; model: string; temperature: number | null; max_output_tokens: number };
  active_run_id: string | null;
  draft: string;
  latest_run: Run | null;
}

export interface MessageResponse {
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
}

export interface SubmissionResponse {
  submission_id: string;
  evaluation_id: string;
}
export interface EvidenceReference {
  kind: "submission" | "trace" | "artifact" | "usage";
  reference: string;
}

export interface EvaluationResult {
  id: string;
  status: "completed" | "failed" | "unsupported";
  session_id: string;
  submission_id: string;
  problem_id: string;
  problem_version: string;
  score: number | null;
  maximum_score: number | null;
  criteria: {
    id: string;
    title: string;
    score: number | null;
    maximum_score: number | null;
    passed: boolean | null;
    status?: "completed" | "failed" | "unsupported";
    evaluator_version?: string | null;
    feedback: string;
    evidence: EvidenceReference[];
  }[];
  feedback: string[];
  evidence: EvidenceReference[];
  evaluator_id: string;
  evaluator_version: string;
  trace_availability?: "available" | "expired" | "unavailable";
  trace_integrity?: { status: string; reason: string | null; event_count: number; head_hash: string | null } | null;
}

export interface TraceEvent {
  event_id: string;
  session_id: string;
  sequence_number: number;
  event_type: string;
  timestamp: string;
  payload: Record<string, unknown>;
  schema_version: string;
  source: "server" | "external";
  actor: string;
  resource_ids: Record<string, string>;
  correlation_id?: string | null;
  parent_event_id?: string | null;
  previous_hash?: string | null;
  event_hash?: string | null;
}

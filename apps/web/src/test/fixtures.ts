import type {
  EvaluationResult,
  Problem,
  SolveSession,
  SessionUsage,
  RuntimeOptions,
  TraceEvent,
} from "../types";

export const problem: Problem = {
  id: "release-plan",
  version: "1.0.0",
  title: "A thoughtful release plan",
  description:
    "Work with AI to prepare a clear release plan for a small software project.",
  category: "Planning",
  difficulty: "Introductory",
  initial_resources: [
    {
      name: "Brief",
      content: "A small team is shipping a new feature.",
      media_type: "text/plain",
    },
  ],
  allowed_ai_capabilities: ["chat"],
  allowed_tools: [],
  resource_limits: {
    max_messages: 3,
    max_message_chars: 2000,
    max_submission_chars: 10000,
  },
  submission: {
    kind: "text",
    instructions: "Explain the goal, verification, and risk.",
  },
  evaluation: {
    evaluator_id: "builtin.text-rubric",
    evaluator_version: "1.0.0",
    criteria: [
      {
        id: "goal",
        title: "Clear goal",
        description: "Explain what success looks like.",
        max_score: 10,
      },
    ],
  },
};
export const session: SolveSession = {
  id: "session-123",
  problem_id: problem.id,
  problem_version: problem.version,
  status: "active",
  messages: [],
  submission_id: null,
  evaluation_id: null,
  created_at: "2026-11-09T08:00:00Z",
  runtime_profile: "mock",
  model_configuration: { provider: "mock", model: "mock-v1", temperature: 0, max_output_tokens: 1024 },
  active_run_id: null,
  draft: "",
  latest_run: null,
};
export const runtimeOptions: RuntimeOptions = {
  default_profile: "mock",
  profiles: [{ id: "mock", label: "Mock provider", model: "mock-v1", capabilities: { tools: true, system_messages: true, temperature: true, token_limit_parameter: "max_tokens" } }],
};
export const usage: SessionUsage = {
  model_calls: 0,
  tool_calls: 0,
  input_tokens: 0,
  output_tokens: 0,
  estimated: true,
  usage_complete: true,
  cost_estimate: null,
  cost_estimate_complete: false,
  currency: null,
  limits: { ...problem.resource_limits, max_model_calls: 30, max_tool_calls: 20 },
};
export const result: EvaluationResult = {
  id: "evaluation-123",
  status: "completed",
  session_id: session.id,
  submission_id: "submission-123",
  problem_id: problem.id,
  problem_version: problem.version,
  score: 10,
  maximum_score: 10,
  criteria: [
    {
      id: "goal",
      title: "Clear goal",
      score: 10,
      maximum_score: 10,
      passed: true,
      feedback: "The goal criterion is satisfied.",
      evidence: [{ kind: "submission", reference: "submission-123" }],
    },
  ],
  feedback: ["Your plan meets the sample rubric."],
  evidence: [{ kind: "submission", reference: "submission-123" }],
  evaluator_id: "builtin.text-rubric",
  evaluator_version: "1.0.0",
};
export const trace: TraceEvent[] = [
  {
    event_id: "event-1",
    session_id: session.id,
    sequence_number: 1,
    event_type: "SESSION_STARTED",
    timestamp: "2026-11-09T08:00:00Z",
    payload: { problem_version: problem.version },
    schema_version: "1.0",
    source: "server",
    actor: "system",
    resource_ids: {},
  },
  {
    event_id: "event-2",
    session_id: session.id,
    sequence_number: 2,
    event_type: "EVALUATION_COMPLETED",
    timestamp: "2026-11-09T08:00:30Z",
    payload: { evaluation_id: result.id },
    schema_version: "1.0",
    source: "server",
    actor: "system",
    resource_ids: {},
  },
];

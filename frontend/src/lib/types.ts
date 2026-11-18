export interface User {
  id: number;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Position {
  x: number;
  y: number;
}

export interface GraphNode {
  id: string;
  type: string;
  label?: string | null;
  position: Position;
  config: Record<string, unknown>;
  disabled?: boolean;
  retry_attempts?: number;
  retry_delay_seconds?: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  label?: string | null;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  viewport?: Record<string, number> | null;
}

export interface WorkflowSummary {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  version: number;
  user_id: number;
  created_at: string;
  updated_at: string;
  node_count: number;
  edge_count: number;
  trigger_types: string[];
}

export interface Workflow extends WorkflowSummary {
  graph: Graph;
  webhook_url: string | null;
  schedule_cron: string | null;
}

export interface WorkflowVersionSummary {
  id: number;
  workflow_id: number;
  version: number;
  name: string;
  description: string | null;
  origin: string;
  created_by: number | null;
  created_at: string;
  node_count: number;
  edge_count: number;
}

export interface WorkflowVersionDetail extends WorkflowVersionSummary {
  graph: Graph;
}

export type ExecutionStatus =
  | "pending"
  | "queued"
  | "running"
  | "success"
  | "failed"
  | "cancelled";

export interface ExecutionSummary {
  id: number;
  workflow_id: number;
  user_id: number;
  status: ExecutionStatus | string;
  trigger: string;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  steps: number;
  created_at: string;
  workflow_name: string | null;
}

export interface ExecutionLog {
  id: number;
  node_id: string | null;
  node_type: string | null;
  node_name: string | null;
  status: string;
  attempt: number;
  message: string | null;
  error: string | null;
  input: unknown;
  output: unknown;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface ExecutionDetail extends ExecutionSummary {
  trigger_data: Record<string, unknown> | null;
  input: Record<string, unknown> | null;
  output: unknown;
  logs: ExecutionLog[];
}

export interface ExecutionList {
  total: number;
  limit: number;
  offset: number;
  items: ExecutionSummary[];
}

export interface DashboardStats {
  workflows: { total: number; active: number };
  executions: {
    total: number;
    by_status: Record<string, number>;
    success_rate: number;
    avg_duration_ms: number | null;
  };
  ai: { tokens: number; cost_usd: number };
  daily: Array<Record<string, number | string>>;
  recent_executions: ExecutionSummary[];
  upcoming_schedules: Array<{
    id: number;
    workflow_id: number;
    workflow_name: string;
    node_id: string;
    cron: string;
    timezone: string;
    next_run_at: string | null;
    last_run_at: string | null;
  }>;
}

export interface NodeCatalogEntry {
  type: string;
  label: string;
  description: string;
  category: string;
  category_label: string;
  outputs: string[];
  is_trigger: boolean;
  dynamic_outputs: boolean;
  config_schema: {
    type?: string;
    properties?: Record<string, JsonSchemaProperty>;
    required?: string[];
    $defs?: Record<string, JsonSchemaProperty>;
  };
  defaults: Record<string, unknown>;
}

export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  anyOf?: JsonSchemaProperty[];
  items?: JsonSchemaProperty;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  additionalProperties?: JsonSchemaProperty | boolean;
  $ref?: string;
}

export interface NodeCatalog {
  nodes: NodeCatalogEntry[];
  categories: Array<{ key: string; label: string }>;
}

export interface ValidationIssue {
  severity: string;
  node_id: string | null;
  message: string;
}

export interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

export interface GeneratedWorkflow {
  graph: Graph;
  issues: ValidationIssue[];
  provider: string;
  model: string;
  provider_label: string | null;
  explanation: string | null;
}

export interface Credential {
  id: number;
  name: string;
  type: string;
  fields: string[];
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AIProvider {
  name: string;
  label: string;
  configured: boolean;
  requires_api_key: boolean;
  default_model: string;
  models: string[];
  is_default: boolean;
}

export interface AIProviderList {
  default_provider: string;
  default_model: string;
  providers: AIProvider[];
}

export interface AIUsage {
  days?: number;
  total_tokens?: number;
  total_cost_usd?: number;
  by_provider?: Array<Record<string, unknown>>;
  by_model?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface WebhookInfo {
  configured: boolean;
  url: string | null;
  node_id: string | null;
  method?: string;
  secret_configured?: boolean;
  require_signature?: boolean;
}

export interface WebhookSecret {
  node_id: string;
  secret?: string;
  [key: string]: unknown;
}

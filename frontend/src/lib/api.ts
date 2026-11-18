import { clearSession, getToken } from "./session";
import type {
  AIProviderList,
  AIUsage,
  Credential,
  DashboardStats,
  ExecutionDetail,
  ExecutionList,
  ExecutionSummary,
  GeneratedWorkflow,
  Graph,
  LoginResponse,
  NodeCatalog,
  User,
  ValidationResult,
  WebhookInfo,
  WebhookSecret,
  Workflow,
  WorkflowSummary,
  WorkflowVersionSummary,
} from "./types";


const API_BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (response.status === 401) {
    clearSession();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
  }

  if (!response.ok) {
    let message = `Falha na requisição (${response.status}).`;
    let details: unknown;
    try {
      const payload = await response.json();
      message = payload?.error?.message ?? payload?.detail ?? message;
      details = payload?.error?.details ?? payload;
      if (Array.isArray(payload?.detail)) {
        message = payload.detail
          .map((item: { msg?: string }) => item.msg ?? "Valor inválido")
          .join(" ");
      }
    } catch {
      // Non-JSON error bodies keep the generic message.
    }
    throw new ApiError(message, response.status, details);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<LoginResponse>("/auth/login", { method: "POST", body: { email, password } }),
  register: (name: string, email: string, password: string) =>
    request<User>("/auth/register", { method: "POST", body: { name, email, password } }),
  me: () => request<User>("/auth/me"),
  updateMe: (payload: { name?: string; email?: string }) =>
    request<User>("/auth/me", { method: "PATCH", body: payload }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/auth/change-password", {
      method: "POST",
      body: { current_password, new_password },
    }),
  forgotPassword: (email: string) =>
    request<{ detail: string; dev_token?: string }>("/auth/forgot-password", {
      method: "POST",
      body: { email },
    }),
  resetPassword: (token: string, new_password: string) =>
    request<{ detail: string }>("/auth/reset-password", {
      method: "POST",
      body: { token, new_password },
    }),


  dashboard: () => request<DashboardStats>("/dashboard/stats"),

  workflows: (search?: string) =>
    request<WorkflowSummary[]>(
      `/workflows${search ? `?search=${encodeURIComponent(search)}` : ""}`,
    ),
  workflow: (id: number) => request<Workflow>(`/workflows/${id}`),
  createWorkflow: (name: string, description?: string) =>
    request<Workflow>("/workflows", {
      method: "POST",
      body: { name, description: description || null },
    }),
  updateWorkflow: (
    id: number,
    payload: {
      name?: string;
      description?: string | null;
      is_active?: boolean;
      graph?: Graph;
    },
  ) => request<Workflow>(`/workflows/${id}`, { method: "PATCH", body: payload }),
  deleteWorkflow: (id: number) => request<void>(`/workflows/${id}`, { method: "DELETE" }),
  runWorkflow: (id: number, input: Record<string, unknown> = {}) =>
    request<ExecutionSummary>(`/workflows/${id}/run`, { method: "POST", body: { input } }),
  validateWorkflow: (graph: Graph) =>
    request<ValidationResult>("/workflows/validate", { method: "POST", body: graph }),
  generateWorkflow: (prompt: string, provider?: string, model?: string) =>
    request<GeneratedWorkflow>("/workflows/generate", {
      method: "POST",
      body: { prompt, provider: provider || null, model: model || null },
    }),
  duplicateWorkflow: (id: number, name?: string) =>
    request<Workflow>(`/workflows/${id}/duplicate`, {
      method: "POST",
      body: name ? { name } : {},
    }),
  webhookInfo: (id: number) => request<WebhookInfo>(`/workflows/${id}/webhook`),
  workflowVersions: (id: number) =>
    request<WorkflowVersionSummary[]>(`/workflows/${id}/versions`),
  restoreWorkflowVersion: (id: number, version: number) =>
    request<Workflow>(`/workflows/${id}/versions/${version}/restore`, {
      method: "POST",
    }),

  rotateWebhook: (id: number, nodeId?: string, nodeType = "trigger_webhook") => {
    const params = new URLSearchParams({ node_type: nodeType });
    if (nodeId) params.set("node_id", nodeId);
    return request<WebhookSecret>(`/workflows/${id}/webhook/rotate?${params}`, {
      method: "POST",
    });
  },

  executions: (params: {
    workflowId?: number;
    status?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const search = new URLSearchParams();
    if (params.workflowId) search.set("workflow_id", String(params.workflowId));
    if (params.status) search.set("status", params.status);
    search.set("limit", String(params.limit ?? 50));
    search.set("offset", String(params.offset ?? 0));
    return request<ExecutionList>(`/executions?${search}`);
  },
  execution: (id: number) => request<ExecutionDetail>(`/executions/${id}`),
  retryExecution: (id: number) =>
    request<ExecutionSummary>(`/executions/${id}/retry`, { method: "POST" }),
  cancelExecution: (id: number) =>
    request<ExecutionSummary>(`/executions/${id}/cancel`, { method: "POST" }),

  catalog: () => request<NodeCatalog>("/nodes"),

  credentials: () => request<Credential[]>("/credentials"),
  credentialTypes: () =>
    request<{ types: Array<{ type: string; label: string; fields: Array<{ name: string; secret: boolean }> }> }>(
      "/credentials/types",
    ),
  createCredential: (payload: { name: string; type: string; data: Record<string, unknown> }) =>
    request<Credential>("/credentials", { method: "POST", body: payload }),
  updateCredential: (id: number, payload: { name?: string; data?: Record<string, unknown> }) =>
    request<Credential>(`/credentials/${id}`, { method: "PATCH", body: payload }),
  deleteCredential: (id: number) =>
    request<void>(`/credentials/${id}`, { method: "DELETE" }),

  aiProviders: () => request<AIProviderList>("/ai/providers"),
  aiUsage: (days = 30) => request<AIUsage>(`/ai/usage?days=${days}`),

  notifications: () =>
    request<{
      items: Array<{
        id: number;
        title: string;
        body: string | null;
        level: string;
        execution_id: number | null;
        read: boolean;
        created_at: string;
      }>;
      unread: number;
    }>("/notifications"),
  markNotificationRead: (id: number) =>
    request<unknown>(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () =>
    request<unknown>("/notifications/read-all", { method: "POST" }),
};


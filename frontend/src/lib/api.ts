import { ModelOption, TaskDetail, TaskSummary } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const AUTH_TOKEN = process.env.NEXT_PUBLIC_DEV_BEARER_TOKEN ?? "orchestrator-dev-token";
const DEV_USER = process.env.NEXT_PUBLIC_DEV_USER ?? "web-user";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${AUTH_TOKEN}`,
      "X-Dev-User": DEV_USER,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body}`);
  }

  return (await response.json()) as T;
}

export const api = {
  listTasks: () => request<TaskSummary[]>("/api/tasks"),
  getTask: (taskId: string) => request<TaskDetail>(`/api/tasks/${taskId}`),
  listModels: () => request<ModelOption[]>("/api/models"),
  createTask: (input: {
    title: string;
    description: string;
    github_url: string;
    model_provider?: string;
    model_id?: string;
  }) =>
    request<TaskSummary>("/api/tasks", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  sendMessage: (taskId: string, content: string) =>
    request<{ ok: boolean }>(`/api/tasks/${taskId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
  approvePlan: (taskId: string, key: string) =>
    request<Record<string, unknown>>(`/api/tasks/${taskId}/approve-plan`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
    }),
  requestReview: (taskId: string, key: string) =>
    request<Record<string, unknown>>(`/api/tasks/${taskId}/request-review`, {
      method: "POST",
      headers: { "Idempotency-Key": key },
    }),
  stopTask: (taskId: string) =>
    request<{ ok: boolean }>(`/api/tasks/${taskId}/stop`, {
      method: "POST",
    }),
};

export function taskStreamUrl(taskId: string): string {
  const url = new URL(`${API_BASE_URL}/api/tasks/${taskId}/stream`);
  url.searchParams.set("token", AUTH_TOKEN);
  url.searchParams.set("user", DEV_USER);
  return url.toString();
}

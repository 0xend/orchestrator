export type TaskStatus =
  | "planning"
  | "plan_review"
  | "implementing"
  | "code_review"
  | "complete"
  | "failed"
  | "canceled";

export interface TaskSummary {
  id: string;
  owner_user_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  repo_name: string;
  github_url: string;
  worktree_path: string | null;
  branch_name: string | null;
  preview_url: string | null;
  plan_markdown: string | null;
  pr_url: string | null;
  version: number;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SessionMessage {
  id: number;
  role: "user" | "assistant" | "tool_use" | "tool_result";
  content: Record<string, unknown>;
  created_at: string | null;
}

export interface TaskSession {
  id: string;
  agent_role: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  messages: SessionMessage[];
}

export interface TaskDetail extends TaskSummary {
  sessions: TaskSession[];
}

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

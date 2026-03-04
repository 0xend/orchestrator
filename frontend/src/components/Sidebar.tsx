import Link from "next/link";

import { TaskSummary } from "@/lib/types";

interface SidebarProps {
  tasks: TaskSummary[];
  selectedTaskId?: string;
}

export function Sidebar({ tasks, selectedTaskId }: SidebarProps) {
  return (
    <aside className="sidebar">
      <h2 style={{ marginTop: 0 }}>Orchestrator</h2>
      <p style={{ color: "var(--muted)", marginTop: 0 }}>Tasks</p>
      {tasks.map((task) => (
        <Link
          key={task.id}
          href={`/tasks/${task.id}`}
          className={`task-link ${selectedTaskId === task.id ? "active" : ""}`}
        >
          <div style={{ fontWeight: 600 }}>{task.title}</div>
          <div style={{ color: "var(--muted)", fontSize: 13 }}>{task.status}</div>
        </Link>
      ))}
      {tasks.length === 0 ? <div style={{ color: "var(--muted)" }}>No tasks yet.</div> : null}
    </aside>
  );
}

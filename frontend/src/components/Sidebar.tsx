import Link from "next/link";

import { TaskSummary } from "@/lib/types";

interface SidebarProps {
  tasks: TaskSummary[];
  selectedTaskId?: string;
}

export function Sidebar({ tasks, selectedTaskId }: SidebarProps) {
  return (
    <aside className="sidebar">
      <Link href="/" className="sidebar-brand">
        <h2>Orchestrator</h2>
      </Link>
      <div className="section-label">Tasks</div>
      {tasks.map((task) => (
        <Link
          key={task.id}
          href={`/tasks/${task.id}`}
          className={`task-link ${selectedTaskId === task.id ? "active" : ""}`}
        >
          <div className="task-link-title">{task.title}</div>
          <div className="task-link-meta">
            <span className="status-badge" data-status={task.status}>
              {task.status.replace("_", " ")}
            </span>
          </div>
        </Link>
      ))}
      {tasks.length === 0 ? <div className="empty-state">No tasks yet.</div> : null}
    </aside>
  );
}

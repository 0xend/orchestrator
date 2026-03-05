"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { NewTaskDialog } from "@/components/NewTaskDialog";
import { Sidebar } from "@/components/Sidebar";
import { api } from "@/lib/api";
import { TaskSummary } from "@/lib/types";

export default function HomePage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setTasks(await api.listTasks());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function createTask(input: { title: string; description: string; github_url: string }) {
    await api.createTask(input);
    await load();
  }

  return (
    <div className="app-shell">
      <Sidebar tasks={tasks} />
      <main className="main stack-lg">
        <NewTaskDialog onCreate={createTask} />

        <section className="panel">
          <h3>Task List</h3>
          {tasks.map((task) => (
            <Link key={task.id} href={`/tasks/${task.id}`} className="task-link">
              <div className="task-link-title">{task.title}</div>
              <div className="task-link-meta">
                <span className="status-badge" data-status={task.status}>
                  {task.status.replace("_", " ")}
                </span>
                <span>{task.github_url}</span>
              </div>
            </Link>
          ))}
          {tasks.length === 0 ? <div className="empty-state">Create the first task.</div> : null}
        </section>

        {error ? <div className="error-panel">Error: {error}</div> : null}
      </main>
    </div>
  );
}

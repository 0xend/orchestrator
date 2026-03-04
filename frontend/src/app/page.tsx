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
      <main className="main stack">
        <NewTaskDialog onCreate={createTask} />

        <section className="panel">
          <h3 style={{ marginTop: 0 }}>Task List</h3>
          {tasks.map((task) => (
            <Link key={task.id} href={`/tasks/${task.id}`} className="task-link">
              <strong>{task.title}</strong>
              <div style={{ color: "var(--muted)" }}>
                {task.status} • {task.github_url}
              </div>
            </Link>
          ))}
          {tasks.length === 0 ? <div style={{ color: "var(--muted)" }}>Create the first task.</div> : null}
        </section>

        {error ? <section className="panel">Error: {error}</section> : null}
      </main>
    </div>
  );
}

"use client";

import { FormEvent, useState } from "react";

import { RepoConfig } from "@/lib/types";

interface NewTaskDialogProps {
  repos: RepoConfig[];
  onCreate: (input: { title: string; description: string; repo_name: string }) => Promise<void>;
}

export function NewTaskDialog({ repos, onCreate }: NewTaskDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [repoName, setRepoName] = useState(repos[0]?.name ?? "");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title || !description || !repoName) {
      return;
    }

    setBusy(true);
    try {
      await onCreate({ title, description, repo_name: repoName });
      setTitle("");
      setDescription("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel stack" onSubmit={submit}>
      <h3 style={{ margin: 0 }}>New Task</h3>
      <select value={repoName} onChange={(event) => setRepoName(event.target.value)}>
        {repos.map((repo) => (
          <option key={repo.name} value={repo.name}>
            {repo.name}
          </option>
        ))}
      </select>
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="Title"
        required
      />
      <textarea
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="Describe the task"
        rows={4}
        required
      />
      <button className="primary" type="submit" disabled={busy || repos.length === 0}>
        {busy ? "Creating..." : "Create Task"}
      </button>
    </form>
  );
}

"use client";

import { FormEvent, useState } from "react";

interface NewTaskDialogProps {
  onCreate: (input: { title: string; description: string; github_url: string }) => Promise<void>;
}

export function NewTaskDialog({ onCreate }: NewTaskDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title || !description || !githubUrl) {
      return;
    }

    setBusy(true);
    try {
      await onCreate({ title, description, github_url: githubUrl });
      setTitle("");
      setDescription("");
      setGithubUrl("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel stack" onSubmit={submit}>
      <h3>New Task</h3>
      <input
        value={githubUrl}
        onChange={(event) => setGithubUrl(event.target.value)}
        placeholder="https://github.com/owner/repo"
        type="url"
        required
      />
      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="Task title"
        required
      />
      <textarea
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="Describe what needs to be done..."
        rows={4}
        required
      />
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Creating..." : "Create Task"}
      </button>
    </form>
  );
}

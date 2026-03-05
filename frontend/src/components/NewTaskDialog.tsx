"use client";

import { FormEvent, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { ModelOption } from "@/lib/types";

interface NewTaskDialogProps {
  onCreate: (input: {
    title: string;
    description: string;
    github_url: string;
    model_provider?: string;
    model_id?: string;
  }) => Promise<void>;
}

export function NewTaskDialog({ onCreate }: NewTaskDialogProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listModels().then((m) => {
      setModels(m);
      if (m.length > 0) {
        setSelectedModel(`${m[0].provider}::${m[0].model_id}`);
      }
    });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title || !description || !githubUrl) {
      return;
    }

    setBusy(true);
    try {
      const input: {
        title: string;
        description: string;
        github_url: string;
        model_provider?: string;
        model_id?: string;
      } = { title, description, github_url: githubUrl };

      if (selectedModel) {
        const [provider, modelId] = selectedModel.split("::");
        input.model_provider = provider;
        input.model_id = modelId;
      }

      await onCreate(input);
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
      {models.length > 0 && (
        <select
          value={selectedModel}
          onChange={(event) => setSelectedModel(event.target.value)}
        >
          {models.map((m) => (
            <option key={`${m.provider}::${m.model_id}`} value={`${m.provider}::${m.model_id}`}>
              {m.display_name}
            </option>
          ))}
        </select>
      )}
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Creating..." : "Create Task"}
      </button>
    </form>
  );
}

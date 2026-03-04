"use client";

import { FormEvent, useMemo, useState } from "react";

import { MessageBubble } from "@/components/MessageBubble";
import { ToolCallDisplay } from "@/components/ToolCallDisplay";
import { TaskDetail } from "@/lib/types";

interface StreamLog {
  id: string;
  event: string;
  data: Record<string, unknown>;
}

interface ChatPanelProps {
  task: TaskDetail;
  streamLogs: StreamLog[];
  onSend: (content: string) => Promise<void>;
  onApprovePlan: () => Promise<void>;
  onRequestReview: () => Promise<void>;
}

export function ChatPanel({
  task,
  streamLogs,
  onSend,
  onApprovePlan,
  onRequestReview,
}: ChatPanelProps) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const flattenedMessages = useMemo(
    () =>
      task.sessions.flatMap((session) =>
        session.messages.map((msg) => ({
          id: `${session.id}-${msg.id}`,
          role: msg.role,
          text: String(msg.content.text ?? JSON.stringify(msg.content)),
        })),
      ),
    [task.sessions],
  );

  const interactive = task.status === "planning" || task.status === "implementing";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!interactive || !message.trim()) {
      return;
    }

    setBusy(true);
    try {
      await onSend(message.trim());
      setMessage("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel stack">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{task.title}</h3>
        <strong>{task.status}</strong>
      </div>

      <div style={{ maxHeight: 360, overflowY: "auto", paddingRight: 4 }}>
        {flattenedMessages.map((msg) => (
          <MessageBubble
            key={msg.id}
            role={msg.role === "user" ? "user" : "assistant"}
            text={msg.text}
          />
        ))}
        {flattenedMessages.length === 0 ? (
          <div style={{ color: "var(--muted)" }}>No messages yet.</div>
        ) : null}
      </div>

      {streamLogs.length > 0 ? (
        <div className="stack">
          <div style={{ color: "var(--muted)", fontSize: 13 }}>Live stream</div>
          {streamLogs.slice(-4).map((item) =>
            item.event === "tool_use" ? (
              <ToolCallDisplay key={item.id} tool={String(item.data.tool ?? "tool")} input={item.data} />
            ) : (
              <MessageBubble key={item.id} role="tool" text={`${item.event}: ${JSON.stringify(item.data)}`} />
            ),
          )}
        </div>
      ) : null}

      <form onSubmit={submit} className="row">
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Send message"
          disabled={!interactive || busy}
        />
        <button type="submit" className="primary" disabled={!interactive || busy}>
          Send
        </button>
      </form>

      <div className="row">
        <button
          className="primary"
          type="button"
          onClick={() => void onApprovePlan()}
          disabled={task.status !== "planning" || !task.plan_markdown}
        >
          Approve Plan
        </button>
        <button
          className="warn"
          type="button"
          onClick={() => void onRequestReview()}
          disabled={task.status !== "implementing"}
        >
          Request Review
        </button>
      </div>
    </section>
  );
}

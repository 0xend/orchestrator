"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { PreviewFrame } from "@/components/PreviewFrame";
import { Sidebar } from "@/components/Sidebar";
import { api, taskStreamUrl } from "@/lib/api";
import { StreamEvent, TaskDetail, TaskSummary } from "@/lib/types";
import { useEventStream } from "@/lib/useEventStream";

interface StreamLog {
  id: string;
  event: string;
  data: Record<string, unknown>;
}

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const taskId = params.id;

  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [streamLogs, setStreamLogs] = useState<StreamLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  const streamUrl = useMemo(() => taskStreamUrl(taskId), [taskId]);

  async function refresh() {
    try {
      const [taskList, taskDetail] = await Promise.all([api.listTasks(), api.getTask(taskId)]);
      setTasks(taskList);
      setTask(taskDetail);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId]);

  useEventStream(streamUrl, {
    enabled: Boolean(task),
    onEvent: (event: StreamEvent) => {
      setStreamLogs((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random()}`,
          event: event.event,
          data: event.data,
        },
      ]);
      if (event.event === "status_change" || event.event === "plan_ready" || event.event === "review_done") {
        void refresh();
      }
    },
  });

  async function sendMessage(content: string) {
    await api.sendMessage(taskId, content);
    await refresh();
  }

  async function approvePlan() {
    await api.approvePlan(taskId, `approve-${Date.now()}`);
    await refresh();
  }

  async function requestReview() {
    await api.requestReview(taskId, `review-${Date.now()}`);
    await refresh();
  }

  if (!task) {
    return (
      <div className="app-shell">
        <Sidebar tasks={tasks} selectedTaskId={taskId} />
        <main className="main">
          <div className="loading-state">
            <span className="loading-dot" />
            <span className="loading-dot" />
            <span className="loading-dot" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar tasks={tasks} selectedTaskId={taskId} />
      <main className="main stack-lg">
        <ChatPanel
          task={task}
          streamLogs={streamLogs}
          onSend={sendMessage}
          onApprovePlan={approvePlan}
          onRequestReview={requestReview}
        />
        <PreviewFrame previewUrl={task.preview_url} />
        {error ? <div className="error-panel">Error: {error}</div> : null}
      </main>
    </div>
  );
}

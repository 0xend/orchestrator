"use client";

import { useEffect, useRef } from "react";

import { StreamEvent } from "@/lib/types";

interface UseEventStreamOptions {
  enabled: boolean;
  onEvent: (event: StreamEvent) => void;
}

export function useEventStream(url: string, options: UseEventStreamOptions): void {
  const { enabled, onEvent } = options;
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const source = new EventSource(url);
    const listener = (ev: MessageEvent<string>) => {
      const eventType = ev.type || "message";
      let data: Record<string, unknown> = {};
      try {
        data = ev.data ? (JSON.parse(ev.data) as Record<string, unknown>) : {};
      } catch {
        data = { raw: ev.data };
      }

      onEventRef.current({ event: eventType, data });
    };

    source.onmessage = listener;
    source.addEventListener("token", listener);
    source.addEventListener("status_change", listener);
    source.addEventListener("plan_ready", listener);
    source.addEventListener("tool_use", listener);
    source.addEventListener("tool_result", listener);
    source.addEventListener("review_done", listener);

    return () => {
      source.close();
    };
  }, [enabled, url]);
}

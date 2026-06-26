"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { apiBase } from "@/lib/api";
import type {
  AgentMessage,
  AgentRun,
  TraceStep,
} from "@/app/workspace";

const API = apiBase();

type StreamEvent =
  | "start"
  | "token"
  | "reset"
  | "tool"
  | "done"
  | "error";

function messageId(role: AgentMessage["role"]) {
  return `${role}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function useAgentStream() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  const patchLast = useCallback(
    (updater: (message: AgentMessage) => AgentMessage) => {
      setMessages((current) => {
        if (current.length === 0) return current;
        const next = [...current];
        next[next.length - 1] = updater(next[next.length - 1]);
        return next;
      });
    },
    [],
  );

  const handleEvent = useCallback(
    (event: StreamEvent, data: Record<string, unknown>) => {
      if (event === "start") {
        if (typeof data.session_id === "string") {
          sessionIdRef.current = data.session_id;
        }
        return;
      }

      if (event === "token") {
        patchLast((message) => ({
          ...message,
          content: message.content + String(data.text ?? ""),
        }));
        return;
      }

      if (event === "reset") {
        patchLast((message) => ({ ...message, content: "" }));
        return;
      }

      if (event === "tool") {
        patchLast((message) => ({
          ...message,
          run: {
            ...(message.run as AgentRun),
            trace: [
              ...(message.run?.trace ?? []),
              data as unknown as TraceStep,
            ],
          },
        }));
        return;
      }

      if (event === "done") {
        patchLast((message) => ({
          ...message,
          streaming: false,
          content:
            typeof data.answer === "string" ? data.answer : message.content,
          run: {
            trace:
              (data.tool_trace as TraceStep[] | undefined) ??
              message.run?.trace ??
              [],
            latency:
              typeof data.latency_ms === "number" ? data.latency_ms : 0,
            steps: typeof data.steps === "number" ? data.steps : 0,
            sources: Array.isArray(data.sources)
              ? (data.sources as AgentRun["sources"])
              : [],
            completedAt: new Date(),
          },
        }));
        return;
      }

      if (event === "error") {
        const message = String(data.message ?? "Unknown server error");
        setError(message);
        patchLast((current) => ({
          ...current,
          streaming: false,
          content: `Error: ${message}`,
        }));
      }
    },
    [patchLast],
  );

  const send = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed || loading) return;

      setError(null);
      setLoading(true);
      setMessages((current) => [
        ...current,
        {
          id: messageId("user"),
          role: "user",
          content: trimmed,
        },
        {
          id: messageId("assistant"),
          role: "assistant",
          content: "",
          streaming: true,
          run: { trace: [], latency: 0, steps: 0, sources: [] },
        },
      ]);

      try {
        const response = await fetch(`${API}/agent/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: trimmed,
            session_id: sessionIdRef.current,
          }),
        });

        if (!response.ok || !response.body) {
          throw new Error(`server responded ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            let event: StreamEvent = "token";
            let payload = "";

            for (const line of block.split("\n")) {
              if (line.startsWith("event:")) {
                event = line.slice(6).trim() as StreamEvent;
              } else if (line.startsWith("data:")) {
                payload += line.slice(5).trim();
              }
            }

            handleEvent(
              event,
              payload
                ? (JSON.parse(payload) as Record<string, unknown>)
                : {},
            );
            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch (caught) {
        const message =
          caught instanceof Error ? caught.message : "Unknown connection error";
        setError(message);
        patchLast((current) => ({
          ...current,
          streaming: false,
          content: `The assistant is unreachable (${message}). Confirm the backend is running at ${API}.`,
        }));
      } finally {
        setLoading(false);
      }
    },
    [handleEvent, loading, patchLast],
  );

  const run = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((message) => message.role === "assistant" && message.run)?.run,
    [messages],
  );

  return { messages, run, loading, error, send };
}

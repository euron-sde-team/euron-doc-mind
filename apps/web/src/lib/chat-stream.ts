"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { apiUrl, errorFrom, ws, type ApiError } from "@/lib/api";
import { qk } from "@/lib/queries";
import { postEventStream } from "@/lib/sse";
import type { Message, Source } from "@/lib/types";

export type PendingAnswer = {
  question: string;
  text: string;
  sources: Source[];
  status: "retrieving" | "answering" | "error";
  error?: string;
};

/**
 * Sends a question to a conversation over server-sent events. While the answer streams,
 * `pending` holds the question, the retrieved sources and the text so far; when it is done
 * the final message (with citations and token usage) lands in the messages query cache.
 */
export function useChatStream(workspace: string) {
  const client = useQueryClient();
  const [pending, setPending] = useState<PendingAnswer | null>(null);
  const abort = useRef<AbortController | null>(null);

  const ask = useCallback(
    async (conversationId: string, question: string): Promise<boolean> => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      const messagesKey = qk.messages(workspace, conversationId);
      const now = new Date().toISOString();
      client.setQueryData<Message[]>(messagesKey, (old = []) => [
        ...old,
        { id: `pending-${now}`, role: "user", content: question, citations: [], sources: [], usage: null, created_at: now },
      ]);
      setPending({ question, text: "", sources: [], status: "retrieving" });
      let finished = false;
      try {
        const response = await postEventStream(
          apiUrl(`${ws(workspace)}/conversations/${conversationId}/messages/stream`),
          { question },
          (event) => {
            const data = JSON.parse(event.data) as Record<string, unknown>;
            if (event.event === "sources") {
              setPending((p) => p && { ...p, sources: data.sources as Source[], status: "answering" });
            } else if (event.event === "delta") {
              setPending((p) => p && { ...p, text: p.text + String(data.text ?? ""), status: "answering" });
            } else if (event.event === "done") {
              finished = true;
              const message = data.message as Message;
              client.setQueryData<Message[]>(messagesKey, (old = []) => [...old, message]);
              setPending(null);
            } else if (event.event === "error") {
              const error = (data.error ?? {}) as { message?: string };
              setPending((p) => p && { ...p, status: "error", error: error.message ?? "The answer failed." });
            }
          },
          controller.signal,
        );
        if (!response.ok) {
          let body: unknown = null;
          try {
            body = await response.json();
          } catch {
            body = null;
          }
          const error: ApiError = errorFrom(response.status, body);
          setPending((p) => p && { ...p, status: "error", error: error.message });
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setPending((p) => p && { ...p, status: "error", error: "The connection to the API was lost." });
        }
      } finally {
        void client.invalidateQueries({ queryKey: qk.conversations(workspace) });
        void client.invalidateQueries({ queryKey: messagesKey });
      }
      return finished;
    },
    [client, workspace],
  );

  const cancel = useCallback(() => {
    abort.current?.abort();
    setPending(null);
  }, []);

  return { pending, ask, cancel };
}

"use client";

import { RotateCcw } from "lucide-react";

import { BrandMark } from "@/components/brand";
import { AnswerBody } from "@/components/chat/answer-body";
import { AssistantMessage, UserBubble } from "@/components/chat/message-view";
import { SourcesPanel } from "@/components/chat/sources-panel";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/feedback";
import type { PendingAnswer } from "@/lib/chat-stream";
import type { Message } from "@/lib/types";

function Thinking({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-[13.5px] text-muted-foreground">
      <span className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className="size-1.5 animate-pulse-dot rounded-full bg-primary" style={{ animationDelay: `${i * 160}ms` }} />
        ))}
      </span>
      {label}
    </span>
  );
}

export function Thread({
  workspace,
  messages,
  pending,
  onRetry,
}: {
  workspace: string;
  messages: Message[];
  pending: PendingAnswer | null;
  onRetry: (question: string) => void;
}) {
  return (
    <div className="space-y-8">
      {messages.map((message) =>
        message.role === "user" ? (
          <UserBubble key={message.id} content={message.content} />
        ) : (
          <AssistantMessage key={message.id} message={message} workspace={workspace} />
        ),
      )}
      {pending ? (
        <div className="flex gap-3.5" aria-live="polite">
          <BrandMark className="mt-0.5 size-7 shrink-0" />
          <div className="min-w-0 flex-1 space-y-3">
            {pending.status === "error" ? (
              <div className="space-y-2">
                <ErrorNotice message={pending.error ?? "The answer failed."} />
                <Button size="sm" variant="secondary" onClick={() => onRetry(pending.question)}>
                  <RotateCcw /> Try again
                </Button>
              </div>
            ) : pending.text ? (
              <AnswerBody text={pending.text} workspace={workspace} sources={pending.sources} streaming />
            ) : (
              <Thinking label={pending.status === "retrieving" ? "Searching your documents" : "Writing the answer"} />
            )}
            {pending.sources.length && pending.status !== "error" ? (
              <SourcesPanel workspace={workspace} sources={pending.sources} citations={[]} />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

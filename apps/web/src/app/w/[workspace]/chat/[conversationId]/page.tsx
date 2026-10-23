"use client";

import { Filter } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

import { Composer } from "@/components/chat/composer";
import { Thread } from "@/components/chat/thread";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { useChatStream } from "@/lib/chat-stream";
import { useConversations, useMessages } from "@/lib/queries";

function Conversation() {
  const { workspace, conversationId } = useParams<{ workspace: string; conversationId: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const messages = useMessages(workspace, conversationId);
  const conversations = useConversations(workspace);
  const { pending, ask, cancel } = useChatStream(workspace);
  const started = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  const conversation = conversations.data?.find((c) => c.id === conversationId);

  useEffect(() => {
    const question = search.get("q");
    if (!question || started.current || !messages.data || messages.data.length > 0) return;
    started.current = true;
    router.replace(`/w/${workspace}/chat/${conversationId}`, { scroll: false });
    void ask(conversationId, question);
  }, [search, messages.data, ask, conversationId, router, workspace]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.data?.length, pending?.text, pending?.status]);

  if (messages.error) {
    return <EmptyState className="h-full" title="Conversation not found" description={messages.error.message} />;
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="sticky top-0 z-10 border-b border-border/70 bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-12 w-full max-w-3xl items-center justify-between gap-3 px-6">
          <h1 className="truncate text-[13.5px] font-medium">{conversation?.title ?? "Conversation"}</h1>
          {conversation?.document_ids?.length ? (
            <Badge tone="primary">
              <Filter /> {conversation.document_ids.length} document{conversation.document_ids.length > 1 ? "s" : ""}
            </Badge>
          ) : null}
        </div>
      </div>
      <div className="mx-auto w-full max-w-3xl flex-1 px-6 pb-10 pt-8">
        {messages.isLoading ? (
          <div className="space-y-6">
            <Skeleton className="ml-auto h-10 w-2/3 rounded-2xl" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : (
          <Thread
            workspace={workspace}
            messages={messages.data ?? []}
            pending={pending}
            onRetry={(question) => void ask(conversationId, question)}
          />
        )}
        <div ref={bottom} />
      </div>
      <div className="sticky bottom-0 bg-gradient-to-t from-background via-background to-transparent pt-6">
        <div className="mx-auto w-full max-w-3xl px-6 pb-6">
          <Composer
            onSend={(question) => void ask(conversationId, question)}
            onStop={cancel}
            busy={pending !== null && pending.status !== "error"}
            placeholder="Ask a follow-up"
            autoFocus
          />
        </div>
      </div>
    </div>
  );
}

export default function ConversationPage() {
  return (
    <Suspense>
      <Conversation />
    </Suspense>
  );
}

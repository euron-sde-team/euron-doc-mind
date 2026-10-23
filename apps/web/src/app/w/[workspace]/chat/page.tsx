"use client";

import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { ChatEmpty } from "@/components/chat/chat-empty";
import { Composer } from "@/components/chat/composer";
import { useConversations, useCreateConversation, useLibraryStats } from "@/lib/queries";

export default function NewChatPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const stats = useLibraryStats(workspace);
  const conversations = useConversations(workspace);
  const create = useCreateConversation(workspace);

  async function start(question: string) {
    try {
      const conversation = await create.mutateAsync({});
      router.push(`/w/${workspace}/chat/${conversation.id}?q=${encodeURIComponent(question)}`);
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 items-center justify-center px-6 py-14">
        <ChatEmpty
          workspace={workspace}
          stats={stats.data}
          recent={conversations.data ?? []}
          onPick={start}
        />
      </div>
      <div className="from-background via-background sticky bottom-0 bg-gradient-to-t to-transparent pt-6">
        <div className="mx-auto w-full max-w-3xl px-6 pb-6">
          <Composer
            onSend={start}
            busy={create.isPending}
            disabled={stats.data?.ready === 0}
            autoFocus
          />
          <p className="text-subtle mt-2 text-center text-[11.5px]">
            Answers cite your documents. Check the sources for anything that matters.
          </p>
        </div>
      </div>
    </div>
  );
}

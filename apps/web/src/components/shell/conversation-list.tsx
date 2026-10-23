"use client";

import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { useConversationActions, useConversations } from "@/lib/queries";
import type { Conversation } from "@/lib/types";

export function ConversationList({ workspace, onNavigate }: { workspace: string; onNavigate?: () => void }) {
  const conversations = useConversations(workspace);
  const pathname = usePathname();
  const router = useRouter();
  const actions = useConversationActions(workspace);
  const [renaming, setRenaming] = useState<Conversation | null>(null);

  if (conversations.isLoading) {
    return (
      <div className="space-y-1.5 px-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-7" />
        ))}
      </div>
    );
  }
  const items = conversations.data ?? [];
  if (!items.length) {
    return <p className="px-3 py-2 text-[12.5px] text-subtle">No conversations yet.</p>;
  }

  return (
    <>
      <ul className="space-y-0.5">
        {items.map((conversation) => {
          const href = `/w/${workspace}/chat/${conversation.id}`;
          const active = pathname === href;
          return (
            <li key={conversation.id} className="group relative">
              <Link
                href={href}
                onClick={onNavigate}
                className={cn(
                  "block truncate rounded-lg py-1.5 pl-3 pr-8 text-[13px] transition-colors",
                  active ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
                title={conversation.title}
              >
                {conversation.title}
              </Link>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label={`Actions for ${conversation.title}`}
                    className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1 text-subtle opacity-0 transition-opacity hover:bg-card hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
                  >
                    <MoreHorizontal className="size-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="min-w-40">
                  <DropdownMenuItem onSelect={() => setRenaming(conversation)}>
                    <Pencil /> Rename
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    destructive
                    onSelect={async () => {
                      await actions.remove.mutateAsync(conversation.id);
                      toast.success("Conversation deleted");
                      if (active) router.push(`/w/${workspace}/chat`);
                    }}
                  >
                    <Trash2 /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          );
        })}
      </ul>
      <RenameDialog
        conversation={renaming}
        onClose={() => setRenaming(null)}
        onSave={async (title) => {
          if (!renaming) return;
          await actions.rename.mutateAsync({ id: renaming.id, title });
          setRenaming(null);
        }}
      />
    </>
  );
}

function RenameDialog({
  conversation,
  onClose,
  onSave,
}: {
  conversation: Conversation | null;
  onClose: () => void;
  onSave: (title: string) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const open = conversation !== null;

  function submit(event: FormEvent) {
    event.preventDefault();
    void onSave(title.trim());
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next && conversation) setTitle(conversation.title);
        if (!next) onClose();
      }}
    >
      <DialogContent title="Rename conversation" onOpenAutoFocus={() => conversation && setTitle(conversation.title)}>
        <form onSubmit={submit}>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!title.trim()}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

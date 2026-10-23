"use client";

import { Download, MoreHorizontal, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { apiUrl, ws } from "@/lib/api";
import { useDocumentAction } from "@/lib/queries";
import type { DocumentItem } from "@/lib/types";

export function downloadHref(workspace: string, document: DocumentItem): string {
  return apiUrl(`${ws(workspace)}/documents/${document.id}/file`);
}

export function DocumentActions({
  workspace,
  document,
  canEdit,
  onDeleted,
}: {
  workspace: string;
  document: DocumentItem;
  canEdit: boolean;
  onDeleted?: () => void;
}) {
  const actions = useDocumentAction(workspace);
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const [title, setTitle] = useState(document.title);

  async function rename(event: FormEvent) {
    event.preventDefault();
    await actions.rename.mutateAsync({ id: document.id, title: title.trim() });
    toast.success("Document renamed");
    setDialog(null);
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${document.title}`}>
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <a href={downloadHref(workspace, document)} download={document.filename}>
              <Download /> Download original
            </a>
          </DropdownMenuItem>
          {canEdit ? (
            <>
              <DropdownMenuItem
                onSelect={() => {
                  setTitle(document.title);
                  setDialog("rename");
                }}
              >
                <Pencil /> Rename
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={async () => {
                  await actions.reprocess.mutateAsync(document.id);
                  toast.success(`Reprocessing ${document.title}`);
                }}
              >
                <RefreshCw /> Reprocess
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={() => setDialog("delete")}>
                <Trash2 /> Delete
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={dialog === "rename"} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent title="Rename document">
          <form onSubmit={rename}>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={300}
              autoFocus
            />
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => setDialog(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!title.trim() || actions.rename.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={dialog === "delete"} onOpenChange={(open) => !open && setDialog(null)}>
        <DialogContent
          title={`Delete ${document.title}?`}
          description="The file, its index and its citations are removed for everyone in this workspace. This cannot be undone."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={actions.remove.isPending}
              onClick={async () => {
                await actions.remove.mutateAsync(document.id);
                toast.success("Document deleted");
                setDialog(null);
                onDeleted?.();
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

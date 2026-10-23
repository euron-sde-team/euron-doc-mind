"use client";

import { CloudUpload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";

import { Spinner } from "@/components/ui/feedback";
import { cn } from "@/lib/cn";
import { useSystemInfo, useUpload } from "@/lib/queries";

const ACCEPT = ".pdf,.docx,.xlsx,.csv,.pptx,.txt,.md,.markdown,.html,.htm";

export function useFilePicker(onFiles: (files: File[]) => void) {
  const input = useRef<HTMLInputElement>(null);
  const element = (
    <input
      ref={input}
      type="file"
      multiple
      accept={ACCEPT}
      className="sr-only"
      tabIndex={-1}
      aria-hidden
      onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        event.target.value = "";
        if (files.length) onFiles(files);
      }}
    />
  );
  return { open: () => input.current?.click(), element };
}

export function useUploader(workspace: string) {
  const upload = useUpload(workspace);
  const send = async (files: File[]) => {
    try {
      const result = await upload.mutateAsync(files);
      if (result.created.length) {
        toast.success(
          result.created.length === 1
            ? `Uploaded ${result.created[0]?.filename}. Indexing now.`
            : `Uploaded ${result.created.length} files. Indexing now.`,
        );
      }
      for (const duplicate of result.duplicates)
        toast.info(`${duplicate.filename} is already in this workspace.`);
      for (const rejected of result.rejected)
        toast.error(`${rejected.filename}: ${rejected.message}`);
    } catch (error) {
      toast.error((error as Error).message);
    }
  };
  return { send, pending: upload.isPending };
}

export function UploadZone({
  workspace,
  compact = false,
}: {
  workspace: string;
  compact?: boolean;
}) {
  const system = useSystemInfo();
  const { send, pending } = useUploader(workspace);
  const picker = useFilePicker((files) => void send(files));
  const [over, setOver] = useState(false);

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length) void send(files);
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cn(
        "border-input bg-card/60 flex items-center gap-4 rounded-xl border border-dashed transition-colors",
        compact ? "px-4 py-3" : "flex-col justify-center px-6 py-12 text-center",
        over && "border-primary bg-accent/50",
      )}
    >
      {picker.element}
      <span
        className={cn(
          "bg-accent text-accent-foreground flex items-center justify-center rounded-xl",
          compact ? "size-9" : "size-12",
        )}
      >
        {pending ? (
          <Spinner className="text-accent-foreground" />
        ) : (
          <CloudUpload className={compact ? "size-4" : "size-5"} />
        )}
      </span>
      <div className={compact ? "min-w-0 flex-1" : ""}>
        <p className="text-[13.5px] font-medium">
          Drop files here or{" "}
          <button
            type="button"
            onClick={picker.open}
            className="text-primary font-semibold hover:underline"
          >
            browse
          </button>
        </p>
        <p className="text-muted-foreground mt-0.5 text-xs">
          PDF, Word, Excel, CSV, PowerPoint, text, Markdown or HTML, up to{" "}
          {system.data?.max_upload_mb ?? 50} MB each.
        </p>
      </div>
    </div>
  );
}

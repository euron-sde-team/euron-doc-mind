"use client";

import { ChevronDown, FileText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { viewerHref } from "@/components/chat/citation-chip";
import { cn } from "@/lib/cn";
import type { Citation, Source } from "@/lib/types";

export function SourcesPanel({
  workspace,
  sources,
  citations,
}: {
  workspace: string;
  sources: Source[];
  citations: Citation[];
}) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;
  const cited = new Set(citations.map((c) => c.n));
  const ordered = [...sources].sort((a, b) => Number(cited.has(b.n)) - Number(cited.has(a.n)) || a.n - b.n);
  const visible = open ? ordered : ordered.slice(0, 3);

  return (
    <div>
      <div className="grid gap-2 sm:grid-cols-3">
        {visible.map((source) => (
          <Link
            key={source.chunk_id}
            href={viewerHref(workspace, source)}
            className={cn(
              "group rounded-lg border border-border bg-card px-3 py-2 transition-colors hover:border-primary/40 hover:bg-accent/40",
              !cited.has(source.n) && "opacity-75",
            )}
          >
            <span className="flex items-center gap-1.5 text-[12px] font-medium">
              <span className="rounded bg-muted px-1 font-mono text-[10.5px] text-muted-foreground">{source.n}</span>
              <FileText className="size-3.5 text-subtle" />
              <span className="truncate">{source.document_title}</span>
            </span>
            <span className="mt-0.5 block truncate text-[11.5px] text-muted-foreground">{source.location}</span>
          </Link>
        ))}
      </div>
      {sources.length > 3 ? (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="mt-2 inline-flex items-center gap-1 text-[12px] font-medium text-muted-foreground hover:text-foreground"
        >
          <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
          {open ? "Fewer sources" : `All ${sources.length} sources`}
        </button>
      ) : null}
    </div>
  );
}

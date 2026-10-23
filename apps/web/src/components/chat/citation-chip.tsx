"use client";

import { ArrowUpRight, FileText } from "lucide-react";
import Link from "next/link";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/cn";
import type { Citation, Source } from "@/lib/types";

export function viewerHref(
  workspace: string,
  target: { document_id: string; section_ordinal: number; char_start: number; char_end: number },
): string {
  const params = new URLSearchParams({
    section: String(target.section_ordinal),
    start: String(target.char_start),
    end: String(target.char_end),
  });
  return `/w/${workspace}/documents/${target.document_id}?${params}`;
}

export function CitationChip({
  n,
  workspace,
  citation,
  source,
}: {
  n: number;
  workspace: string;
  citation?: Citation;
  source?: Source;
}) {
  const target = citation ?? source;
  const chip = (
    <span
      className={cn(
        "bg-accent text-accent-foreground mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-md px-1 align-middle font-mono text-[10.5px] font-semibold",
        target && "hover:bg-primary hover:text-primary-foreground cursor-pointer transition-colors",
      )}
    >
      {n}
    </span>
  );
  if (!target) return chip;
  const quote = citation?.quote ?? source?.snippet ?? "";
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source ${n}: ${target.document_title}, ${target.location}`}
          className="inline"
        >
          {chip}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[22rem]">
        <div className="flex items-start gap-2.5">
          <span className="bg-accent text-accent-foreground mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg">
            <FileText className="size-3.5" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold">{target.document_title}</p>
            <p className="text-muted-foreground text-xs">{target.location}</p>
          </div>
        </div>
        {quote ? (
          <blockquote className="border-primary/60 text-foreground/90 mt-3 border-l-2 pl-3 text-[13px] leading-relaxed">
            {quote}
          </blockquote>
        ) : null}
        <Link
          href={viewerHref(workspace, target)}
          className="text-primary mt-3 inline-flex items-center gap-1 text-[13px] font-medium hover:underline"
        >
          Open in document <ArrowUpRight className="size-3.5" />
        </Link>
      </PopoverContent>
    </Popover>
  );
}

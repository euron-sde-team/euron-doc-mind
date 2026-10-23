"use client";

import { ArrowLeft, Download, MessageSquareText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
import { toast } from "sonner";

import { downloadHref } from "@/components/documents/document-actions";
import { KindIcon, kindLabel } from "@/components/documents/kind-icon";
import { StatusBadge } from "@/components/documents/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { cn } from "@/lib/cn";
import { formatBytes, formatNumber } from "@/lib/format";
import { sliceHighlight } from "@/lib/highlight";
import { useCreateConversation, useDocument } from "@/lib/queries";
import type { Section } from "@/lib/types";

function SectionText({ text }: { text: string }) {
  return (
    <>
      {text.split("\n\n").map((paragraph, index) => (
        <p key={index} className="whitespace-pre-wrap">
          {paragraph}
        </p>
      ))}
    </>
  );
}

function SectionBody({ section, range }: { section: Section; range: [number, number] | null }) {
  const mark = useRef<HTMLElement>(null);
  useEffect(() => {
    mark.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [range]);
  if (!range) {
    return (
      <div className="space-y-3">
        <SectionText text={section.text} />
      </div>
    );
  }
  const [before, highlighted, after] = sliceHighlight(section.text, range[0], range[1]);
  return (
    <div className="whitespace-pre-wrap">
      {before}
      <mark
        ref={mark}
        className="bg-highlight text-foreground ring-highlight-strong/60 rounded px-0.5 ring-1"
      >
        {highlighted}
      </mark>
      {after}
    </div>
  );
}

function Viewer() {
  const { workspace, documentId } = useParams<{ workspace: string; documentId: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const document = useDocument(workspace, documentId);
  const create = useCreateConversation(workspace);
  const target = params.get("section");
  const start = Number(params.get("start"));
  const end = Number(params.get("end"));
  const targetOrdinal = target === null ? null : Number(target);

  if (document.isLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-6 py-8">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-96" />
      </div>
    );
  }
  if (document.error || !document.data) {
    return (
      <EmptyState
        className="h-full"
        title="Document not found"
        description={document.error?.message}
      />
    );
  }
  const data = document.data;

  async function askAbout() {
    try {
      const conversation = await create.mutateAsync({
        title: `About ${data.title}`,
        document_ids: [data.id],
      });
      router.push(`/w/${workspace}/chat/${conversation.id}`);
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-6 lg:px-10">
      <Link
        href={`/w/${workspace}/documents`}
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-[13px]"
      >
        <ArrowLeft className="size-3.5" /> Documents
      </Link>
      <div className="border-border mt-3 flex flex-wrap items-start justify-between gap-4 border-b pb-5">
        <div className="flex min-w-0 items-start gap-3">
          <KindIcon kind={data.kind} className="size-10" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-tight">{data.title}</h1>
            <p className="text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
              <span>{kindLabel(data.kind)}</span>
              <span aria-hidden>&middot;</span>
              <span>{formatBytes(data.size_bytes)}</span>
              <span aria-hidden>&middot;</span>
              <span>{formatNumber(data.section_count)} sections</span>
              <span aria-hidden>&middot;</span>
              <span>{formatNumber(data.token_count)} tokens</span>
              <StatusBadge document={data} />
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" asChild>
            <a href={downloadHref(workspace, data)} download={data.filename}>
              <Download /> Download
            </a>
          </Button>
          {data.status === "ready" ? (
            <Button onClick={askAbout} disabled={create.isPending}>
              <MessageSquareText /> Ask about this
            </Button>
          ) : null}
        </div>
      </div>
      {data.warnings.length ? (
        <div className="mt-4 space-y-1">
          {data.warnings.map((warning) => (
            <Badge key={warning} tone="warning" className="whitespace-normal">
              {warning}
            </Badge>
          ))}
        </div>
      ) : null}
      {data.status !== "ready" ? (
        <EmptyState
          title={
            data.status === "failed" ? "This document could not be indexed" : "Indexing in progress"
          }
          description={data.error ?? "Sections appear here as soon as processing finishes."}
        />
      ) : (
        <div className="mt-6 grid gap-8 lg:grid-cols-[14rem_minmax(0,1fr)]">
          <nav aria-label="Sections" className="hidden lg:block">
            <ul className="scroll-quiet sticky top-6 max-h-[calc(100dvh-8rem)] space-y-0.5 overflow-y-auto pr-2">
              {data.sections.map((section) => (
                <li key={section.ordinal}>
                  <a
                    href={`#section-${section.ordinal}`}
                    className={cn(
                      "block truncate rounded-lg px-2.5 py-1.5 text-[13px] transition-colors",
                      section.ordinal === targetOrdinal
                        ? "bg-accent text-accent-foreground font-medium"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    {section.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="space-y-5">
            {data.sections.map((section) => {
              const isTarget =
                section.ordinal === targetOrdinal && Number.isFinite(start) && end > start;
              return (
                <section
                  key={section.ordinal}
                  id={`section-${section.ordinal}`}
                  className={cn(
                    "bg-card scroll-mt-6 rounded-xl border px-6 py-5 shadow-sm",
                    isTarget ? "border-primary/40 ring-primary/15 ring-2" : "border-border",
                  )}
                >
                  <header className="mb-3 flex items-center justify-between gap-3">
                    <h2 className="text-muted-foreground text-[13px] font-semibold">
                      {section.label}
                    </h2>
                    <span className="text-subtle text-[11.5px] tabular-nums">
                      {formatNumber(section.token_count)} tokens
                    </span>
                  </header>
                  <div className="text-foreground/90 text-[14px] leading-7">
                    <SectionBody section={section} range={isTarget ? [start, end] : null} />
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DocumentViewerPage() {
  return (
    <Suspense>
      <Viewer />
    </Suspense>
  );
}

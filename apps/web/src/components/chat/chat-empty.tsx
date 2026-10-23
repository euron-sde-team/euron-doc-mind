"use client";

import { FileUp, Sparkles } from "lucide-react";
import Link from "next/link";

import { BrandMark } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import type { Conversation, LibraryStats } from "@/lib/types";

const DEFAULT_SUGGESTIONS = [
  "Summarise the key decisions in these documents",
  "What deadlines or dates are mentioned?",
  "Which numbers matter most here?",
];

export function ChatEmpty({
  workspace,
  stats,
  recent,
  onPick,
}: {
  workspace: string;
  stats?: LibraryStats;
  recent: Conversation[];
  onPick: (question: string) => void;
}) {
  const suggestions = recent.length ? recent.slice(0, 4).map((c) => c.title) : DEFAULT_SUGGESTIONS;
  const empty = stats !== undefined && stats.ready === 0;
  return (
    <div className="flex flex-col items-center text-center">
      <BrandMark className="size-11" />
      <h1 className="mt-5 text-[26px] font-semibold tracking-tight">Ask your documents</h1>
      <p className="mt-2 max-w-md text-[14px] text-muted-foreground">
        {empty
          ? "Upload a few files first. DocMind reads PDFs, Word, Excel, CSV, PowerPoint, text, Markdown and HTML."
          : stats
            ? `Answers come only from the ${formatNumber(stats.ready)} documents in this workspace, with a citation for every claim.`
            : "Answers come only from this workspace's documents, with a citation for every claim."}
      </p>
      {empty ? (
        <Button asChild className="mt-6">
          <Link href={`/w/${workspace}/documents`}>
            <FileUp /> Upload documents
          </Link>
        </Button>
      ) : (
        <div className="mt-7 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
          {suggestions.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onPick(question)}
              className="group flex items-start gap-2.5 rounded-xl border border-border bg-card px-3.5 py-3 text-left text-[13.5px] shadow-sm transition-colors hover:border-primary/40 hover:bg-accent/40"
            >
              <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
              <span className="line-clamp-2">{question}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

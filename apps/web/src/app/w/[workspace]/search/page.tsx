"use client";

import { ArrowUpRight, FileText, Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { viewerHref } from "@/components/chat/citation-chip";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNotice, Spinner } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { snippetRuns } from "@/lib/highlight";
import { useSearch } from "@/lib/queries";

const EXAMPLES = ["parental leave", "service credits", "LiDAR supplier", "battery life"];

function Snippet({ text }: { text: string }) {
  return (
    <p className="mt-2 text-[13.5px] leading-relaxed text-foreground/85">
      {snippetRuns(text).map((run, index) =>
        run.match ? (
          <mark key={index} className="rounded bg-highlight px-0.5 font-medium text-foreground">
            {run.text}
          </mark>
        ) : (
          <span key={index}>{run.text}</span>
        ),
      )}
    </p>
  );
}

export default function SearchPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const search = useSearch(workspace);
  const [query, setQuery] = useState("");

  function run(event?: FormEvent, value = query) {
    event?.preventDefault();
    if (value.trim()) search.mutate({ query: value.trim(), limit: 15 });
  }

  return (
    <PageBody className="max-w-4xl">
      <PageHeader title="Search" description="Hybrid search: passages that match the meaning and the words, ranked together." />
      <form onSubmit={run} className="flex gap-2">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-subtle" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search every document in this workspace"
            className="h-11 pl-10 text-[15px]"
            aria-label="Search query"
            autoFocus
          />
        </div>
        <Button type="submit" size="lg" className="h-11" disabled={!query.trim() || search.isPending}>
          {search.isPending ? <Spinner className="text-primary-foreground" /> : null} Search
        </Button>
      </form>
      {search.error ? <ErrorNotice className="mt-4" message={search.error.message} /> : null}
      {search.data ? (
        <div className="mt-6">
          <p className="mb-3 text-[12.5px] text-muted-foreground">
            {search.data.hits.length} passages for &ldquo;{search.data.query}&rdquo; in {search.data.took_ms} ms
          </p>
          {search.data.hits.length ? (
            <ul className="space-y-3">
              {search.data.hits.map((hit) => (
                <li key={hit.chunk_id}>
                  <Link
                    href={viewerHref(workspace, hit)}
                    className="group block rounded-xl border border-border bg-card px-5 py-4 shadow-sm transition-colors hover:border-primary/40"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <FileText className="size-4 shrink-0 text-subtle" />
                        <span className="truncate text-[13.5px] font-semibold group-hover:text-primary">{hit.document_title}</span>
                        <span className="shrink-0 text-[12.5px] text-muted-foreground">{hit.location}</span>
                      </div>
                      <ArrowUpRight className="size-4 shrink-0 text-subtle transition-colors group-hover:text-primary" />
                    </div>
                    {hit.heading && hit.heading !== hit.location ? (
                      <p className="mt-1 text-xs text-subtle">{hit.heading}</p>
                    ) : null}
                    <Snippet text={hit.snippet} />
                    <p className="mt-2.5 flex gap-3 text-[11.5px] text-subtle">
                      {hit.vector_score !== null ? <span>meaning {hit.vector_score.toFixed(2)}</span> : null}
                      {hit.keyword_score !== null ? <span>keywords {hit.keyword_score.toFixed(2)}</span> : null}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon={<SearchIcon />} title="No passages found" description="Try fewer or different words." />
          )}
        </div>
      ) : (
        <div className="mt-8 flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
          <span>Try:</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => {
                setQuery(example);
                run(undefined, example);
              }}
              className="rounded-full border border-border bg-card px-3 py-1 transition-colors hover:border-primary/40 hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      )}
    </PageBody>
  );
}

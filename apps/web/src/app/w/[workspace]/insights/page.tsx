"use client";

import { BookOpen, Clock3, Coins, MessagesSquare, Zap } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";

import { QuestionsChart, TokensChart } from "@/components/insights/charts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { formatBytes, formatCompact, formatDuration, formatNumber, formatPercent } from "@/lib/format";
import { useInsights } from "@/lib/queries";

function Kpi({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return (
    <Card className="px-5 py-4">
      <div className="flex items-center gap-2 text-[12.5px] font-medium text-muted-foreground [&_svg]:size-4 [&_svg]:text-primary">
        {icon}
        {label}
      </div>
      <p className="mt-2 text-[26px] font-semibold tabular-nums tracking-tight">{value}</p>
      <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>
    </Card>
  );
}

export default function InsightsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const [days, setDays] = useState(14);
  const insights = useInsights(workspace, days);
  const data = insights.data;
  const maxCitations = Math.max(1, ...(data?.top_documents.map((d) => d.citations) ?? [1]));

  return (
    <PageBody>
      <PageHeader
        title="Insights"
        description="What people ask, what it costs, and how much retrieval and caching save."
        actions={
          <NativeSelect value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36" aria-label="Time range">
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </NativeSelect>
        }
      />
      {insights.error ? <ErrorNotice message={insights.error.message} /> : null}
      {!data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              icon={<MessagesSquare />}
              label="Questions answered"
              value={formatNumber(data.totals.questions)}
              detail={`${formatNumber(data.totals.searches)} searches as well`}
            />
            <Kpi
              icon={<Coins />}
              label="Tokens saved"
              value={formatCompact(data.totals.saved_tokens)}
              detail={`${formatPercent(data.totals.saved_ratio, 1)} less than pasting every document`}
            />
            <Kpi
              icon={<Zap />}
              label="Cache hit rate"
              value={formatPercent(data.totals.cache_hit_rate)}
              detail={`${formatNumber(data.totals.cache_hits)} answers served instantly`}
            />
            <Kpi
              icon={<Clock3 />}
              label="Median answer time"
              value={formatDuration(data.totals.p50_latency_ms)}
              detail={`95th percentile ${formatDuration(data.totals.p95_latency_ms)}`}
            />
          </div>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Document tokens per day</CardTitle>
                  <CardDescription>What retrieval sent, against pasting every document in scope.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {data.totals.questions ? <TokensChart daily={data.daily} /> : <EmptyState title="No questions yet" />}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Questions per day</CardTitle>
                  <CardDescription>Fresh answers and answers from the cache.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {data.totals.questions ? <QuestionsChart daily={data.daily} /> : <EmptyState title="No questions yet" />}
              </CardContent>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Most cited documents</CardTitle>
                  <CardDescription>Where answers come from.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                {data.top_documents.length ? (
                  <ul className="space-y-3">
                    {data.top_documents.map((doc) => (
                      <li key={doc.document_id}>
                        <div className="mb-1 flex items-center justify-between gap-3 text-[13px]">
                          <Link href={`/w/${workspace}/documents/${doc.document_id}`} className="truncate font-medium hover:text-primary">
                            {doc.title}
                          </Link>
                          <span className="tabular-nums text-muted-foreground">{formatNumber(doc.citations)}</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${(doc.citations / maxCitations) * 100}%` }} />
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState icon={<BookOpen />} title="No citations yet" />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Library and models</CardTitle>
                  <CardDescription>What answers are built from.</CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-[13px]">
                  {[
                    ["Documents ready", `${formatNumber(data.library.ready)} of ${formatNumber(data.library.documents)}`],
                    ["Indexed passages", formatNumber(data.library.chunks)],
                    ["Indexed tokens", formatNumber(data.library.tokens)],
                    ["Storage", formatBytes(data.library.bytes)],
                    ["Answering", data.generator === "extractive" ? "Local extractive" : data.generator],
                    ["Embeddings", data.embeddings],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-xs text-muted-foreground">{label}</dt>
                      <dd className="mt-0.5 truncate font-medium">{value}</dd>
                    </div>
                  ))}
                </dl>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </PageBody>
  );
}

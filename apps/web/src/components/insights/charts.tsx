"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCompact, formatNumber } from "@/lib/format";
import type { Insights } from "@/lib/types";

const axis = { fontSize: 11, fill: "var(--subtle)" };

function dayLabel(day: string): string {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

type TooltipEntry = { name?: string; value?: number; color?: string };

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="border-border bg-card rounded-lg border px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium">{label ? dayLabel(label) : ""}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="text-muted-foreground flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ background: entry.color }} />
          {entry.name}:{" "}
          <span className="text-foreground font-medium">{formatNumber(entry.value ?? 0)}</span>
        </p>
      ))}
    </div>
  );
}

export function TokensChart({ daily }: { daily: Insights["daily"] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={daily} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="baseline" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-2)" stopOpacity={0.6} />
            <stop offset="100%" stopColor="var(--chart-2)" stopOpacity={0.05} />
          </linearGradient>
          <linearGradient id="sent" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.9} />
            <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0.25} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="day"
          tickFormatter={dayLabel}
          tick={axis}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis
          tickFormatter={formatCompact}
          tick={axis}
          tickLine={false}
          axisLine={false}
          width={48}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--input)" }} />
        <Area
          type="monotone"
          dataKey="baseline_tokens"
          name="Paste everything"
          stroke="var(--chart-2)"
          fill="url(#baseline)"
          strokeWidth={1.5}
        />
        <Area
          type="monotone"
          dataKey="context_tokens"
          name="Actually sent"
          stroke="var(--chart-1)"
          fill="url(#sent)"
          strokeWidth={2}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function QuestionsChart({ daily }: { daily: Insights["daily"] }) {
  const data = daily.map((d) => ({ ...d, answered: d.questions - d.cache_hits }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis
          dataKey="day"
          tickFormatter={dayLabel}
          tick={axis}
          tickLine={false}
          axisLine={false}
          minTickGap={24}
        />
        <YAxis allowDecimals={false} tick={axis} tickLine={false} axisLine={false} width={40} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)" }} />
        <Bar
          dataKey="answered"
          name="Answered"
          stackId="q"
          fill="var(--chart-1)"
          radius={[0, 0, 0, 0]}
        />
        <Bar
          dataKey="cache_hits"
          name="From cache"
          stackId="q"
          fill="var(--chart-3)"
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

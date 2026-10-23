import { Clock3, Cpu, Gauge, Zap } from "lucide-react";

import { Tooltip } from "@/components/ui/tooltip";
import { formatDuration, formatNumber, formatPercent } from "@/lib/format";
import type { Usage } from "@/lib/types";

function generatorLabel(generator: string): string {
  return generator === "extractive" ? "Local extractive" : generator.replace(":", " / ");
}

export function TokenMeter({ usage }: { usage: Usage }) {
  const cached = usage.cache !== "miss";
  const used = cached ? 0 : usage.context_tokens;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12px] text-muted-foreground">
      <Tooltip
        content={`Answering used ${formatNumber(used)} document tokens. Pasting every document in scope would have sent ${formatNumber(usage.baseline_tokens)}.`}
      >
        <span className="inline-flex items-center gap-1.5">
          <Gauge className="size-3.5" />
          <span>
            <span className="font-medium text-foreground">{formatNumber(used)}</span> of {formatNumber(usage.baseline_tokens)} tokens
          </span>
          <span className="relative ml-0.5 h-1.5 w-16 overflow-hidden rounded-full bg-muted" aria-hidden>
            <span
              className="absolute inset-y-0 left-0 rounded-full bg-primary"
              style={{ width: `${Math.max(3, (1 - usage.saved_ratio) * 100)}%` }}
            />
          </span>
          <span className="font-medium text-success">{formatPercent(usage.saved_ratio)} saved</span>
        </span>
      </Tooltip>
      {cached ? (
        <span className="inline-flex items-center gap-1 font-medium text-primary">
          <Zap className="size-3.5" /> {usage.cache === "exact" ? "Cached answer" : "Similar question, cached"}
        </span>
      ) : null}
      <span className="inline-flex items-center gap-1">
        <Cpu className="size-3.5" /> {generatorLabel(usage.generator)}
      </span>
      <span className="inline-flex items-center gap-1">
        <Clock3 className="size-3.5" /> {formatDuration(usage.latency_ms)}
      </span>
    </div>
  );
}

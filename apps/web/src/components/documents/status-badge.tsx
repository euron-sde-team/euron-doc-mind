import { AlertCircle, CheckCircle2, Clock4, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import type { DocumentItem } from "@/lib/types";

export function StatusBadge({ document }: { document: DocumentItem }) {
  switch (document.status) {
    case "ready":
      return (
        <Badge tone="success">
          <CheckCircle2 /> Ready
        </Badge>
      );
    case "processing":
      return (
        <Badge tone="primary">
          <Loader2 className="animate-spin" /> Indexing
        </Badge>
      );
    case "queued":
      return (
        <Badge tone="neutral">
          <Clock4 /> Queued
        </Badge>
      );
    default:
      return (
        <Tooltip content={document.error ?? "Processing failed."}>
          <Badge tone="danger" className="cursor-help">
            <AlertCircle /> Failed
          </Badge>
        </Tooltip>
      );
  }
}

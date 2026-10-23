"use client";

import { History } from "lucide-react";

import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { formatRelative } from "@/lib/format";
import { useAudit } from "@/lib/queries";
import type { AuditEvent } from "@/lib/types";

const LABELS: Record<string, (e: AuditEvent) => string> = {
  "workspace.created": () => "created the workspace",
  "workspace.updated": () => "updated workspace settings",
  "member.added": (e) => `added ${String(e.details.email ?? "a member")} as ${String(e.details.role ?? "member")}`,
  "member.role_changed": (e) => `changed a member's role to ${String(e.details.role ?? "")}`,
  "member.removed": () => "removed a member",
  "document.uploaded": (e) => `uploaded ${String(e.details.filename ?? "a document")}`,
  "document.renamed": (e) => `renamed a document to ${String(e.details.title ?? "")}`,
  "document.reprocessed": () => "reprocessed a document",
  "document.deleted": (e) => `deleted ${String(e.details.filename ?? "a document")}`,
  "api_key.created": (e) => `created the API key ${String(e.details.name ?? "")}`,
  "api_key.revoked": (e) => `revoked the API key ${String(e.details.name ?? "")}`,
};

export function ActivityPanel({ workspace }: { workspace: string }) {
  const audit = useAudit(workspace);
  if (audit.isLoading) {
    return <Skeleton className="h-40" />;
  }
  const events = audit.data ?? [];
  return (
    <Card>
      {events.length ? (
        <ol className="divide-y divide-border">
          {events.map((event) => (
            <li key={event.id} className="flex items-start justify-between gap-4 px-5 py-3 text-[13px]">
              <p>
                <span className="font-medium">{event.actor_name ?? "An API key"}</span>{" "}
                <span className="text-muted-foreground">{(LABELS[event.action] ?? (() => event.action))(event)}</span>
              </p>
              <time dateTime={event.created_at} className="shrink-0 text-xs text-subtle">
                {formatRelative(event.created_at)}
              </time>
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState icon={<History />} title="No activity yet" />
      )}
    </Card>
  );
}

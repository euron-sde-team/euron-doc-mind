"use client";

import Link from "next/link";

import { DocumentActions } from "@/components/documents/document-actions";
import { KindIcon, kindLabel } from "@/components/documents/kind-icon";
import { StatusBadge } from "@/components/documents/status-badge";
import { formatBytes, formatNumber, formatRelative } from "@/lib/format";
import type { DocumentItem } from "@/lib/types";

export function DocumentsTable({
  workspace,
  documents,
  canEdit,
}: {
  workspace: string;
  documents: DocumentItem[];
  canEdit: boolean;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <table className="w-full text-left text-[13px]">
        <thead className="border-b border-border bg-muted/50 text-[11.5px] uppercase tracking-wider text-subtle">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">Document</th>
            <th scope="col" className="hidden px-3 py-2.5 font-medium md:table-cell">Contents</th>
            <th scope="col" className="hidden px-3 py-2.5 font-medium sm:table-cell">Size</th>
            <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
            <th scope="col" className="hidden px-3 py-2.5 font-medium lg:table-cell">Added</th>
            <th scope="col" className="w-12 px-2 py-2.5"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {documents.map((document) => (
            <tr key={document.id} className="group transition-colors hover:bg-muted/40">
              <td className="max-w-0 px-4 py-2.5">
                <div className="flex items-center gap-3">
                  <KindIcon kind={document.kind} />
                  <div className="min-w-0">
                    {document.status === "ready" ? (
                      <Link href={`/w/${workspace}/documents/${document.id}`} className="block truncate font-medium hover:text-primary">
                        {document.title}
                      </Link>
                    ) : (
                      <span className="block truncate font-medium">{document.title}</span>
                    )}
                    <span className="block truncate text-xs text-muted-foreground">
                      {kindLabel(document.kind)} &middot; {document.filename}
                    </span>
                  </div>
                </div>
              </td>
              <td className="hidden whitespace-nowrap px-3 py-2.5 text-muted-foreground md:table-cell">
                {document.status === "ready"
                  ? `${formatNumber(document.section_count)} sections, ${formatNumber(document.token_count)} tokens`
                  : "Not indexed yet"}
              </td>
              <td className="hidden whitespace-nowrap px-3 py-2.5 text-muted-foreground sm:table-cell">{formatBytes(document.size_bytes)}</td>
              <td className="px-3 py-2.5">
                <StatusBadge document={document} />
              </td>
              <td className="hidden whitespace-nowrap px-3 py-2.5 text-muted-foreground lg:table-cell">{formatRelative(document.created_at)}</td>
              <td className="px-2 py-2.5 text-right">
                <DocumentActions workspace={workspace} document={document} canEdit={canEdit} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

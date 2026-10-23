"use client";

import { Files, Search, Upload } from "lucide-react";
import { useParams } from "next/navigation";
import { useDeferredValue, useState } from "react";

import { DocumentsTable } from "@/components/documents/documents-table";
import { UploadZone, useFilePicker, useUploader } from "@/components/documents/upload-zone";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { Input, NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { formatBytes, formatCompact, formatNumber } from "@/lib/format";
import { canEdit, useCurrentWorkspace, useDocuments, useLibraryStats } from "@/lib/queries";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-4 py-3">
      <p className="text-[11.5px] font-medium uppercase tracking-wider text-subtle">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums tracking-tight">{value}</p>
    </div>
  );
}

export default function DocumentsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const current = useCurrentWorkspace(workspace);
  const editable = canEdit(current?.role);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const query = useDeferredValue(q);
  const documents = useDocuments(workspace, { q: query, status, kind });
  const stats = useLibraryStats(workspace);
  const uploader = useUploader(workspace);
  const picker = useFilePicker((files) => void uploader.send(files));
  const filtering = Boolean(query || status || kind);
  const items = documents.data?.items ?? [];

  return (
    <PageBody>
      <PageHeader
        title="Documents"
        description="Everything DocMind can answer from in this workspace."
        actions={
          editable ? (
            <>
              {picker.element}
              <Button onClick={picker.open} disabled={uploader.pending}>
                <Upload /> Upload
              </Button>
            </>
          ) : null
        }
      />
      <div className="mb-5 grid grid-cols-2 divide-x divide-border overflow-hidden rounded-xl border border-border bg-card shadow-sm sm:grid-cols-4">
        <Stat label="Documents" value={stats.data ? formatNumber(stats.data.documents) : "..."} />
        <Stat label="Ready" value={stats.data ? formatNumber(stats.data.ready) : "..."} />
        <Stat label="Indexed tokens" value={stats.data ? formatCompact(stats.data.tokens) : "..."} />
        <Stat label="Storage" value={stats.data ? formatBytes(stats.data.bytes) : "..."} />
      </div>
      {editable && (items.length > 0 || filtering) ? <UploadZone workspace={workspace} compact /> : null}
      <div className="mb-3 mt-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by title or file name" className="pl-9" aria-label="Filter documents" />
        </div>
        <NativeSelect value={status} onChange={(e) => setStatus(e.target.value)} className="w-40" aria-label="Status">
          <option value="">All statuses</option>
          <option value="ready">Ready</option>
          <option value="processing">Indexing</option>
          <option value="queued">Queued</option>
          <option value="failed">Failed</option>
        </NativeSelect>
        <NativeSelect value={kind} onChange={(e) => setKind(e.target.value)} className="w-40" aria-label="File type">
          <option value="">All types</option>
          <option value="pdf">PDF</option>
          <option value="docx">Word</option>
          <option value="xlsx">Excel</option>
          <option value="csv">CSV</option>
          <option value="pptx">PowerPoint</option>
          <option value="md">Markdown</option>
          <option value="txt">Text</option>
          <option value="html">HTML</option>
        </NativeSelect>
      </div>
      {documents.error ? <ErrorNotice message={documents.error.message} /> : null}
      {documents.isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      ) : items.length ? (
        <DocumentsTable workspace={workspace} documents={items} canEdit={editable} />
      ) : filtering ? (
        <EmptyState icon={<Search />} title="No documents match" description="Try a different filter." />
      ) : editable ? (
        <UploadZone workspace={workspace} />
      ) : (
        <EmptyState icon={<Files />} title="No documents yet" description="An editor or owner can upload files here." />
      )}
    </PageBody>
  );
}

"use client";

import { Cpu, Database, ScanSearch } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldHint, Label, NativeSelect } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/cn";
import { useSystemInfo, useUpdateWorkspace } from "@/lib/queries";
import type { Workspace, WorkspaceSettings } from "@/lib/types";

const MODES: { value: WorkspaceSettings["answer_mode"]; title: string; text: string }[] = [
  { value: "auto", title: "Best available", text: "Use the configured model; fall back to extractive answers when there is none." },
  { value: "extractive", title: "Extractive only", text: "Never call a model. Answers are built from your documents' own sentences." },
];

export function AnsweringPanel({ workspace, editable }: { workspace: Workspace; editable: boolean }) {
  const system = useSystemInfo();
  const update = useUpdateWorkspace(workspace.slug);
  const [settings, setSettings] = useState<WorkspaceSettings>(workspace.settings);
  const set = <K extends keyof WorkspaceSettings>(key: K, value: WorkspaceSettings[K]) =>
    setSettings((current) => ({ ...current, [key]: value }));

  async function save() {
    try {
      await update.mutateAsync({ settings });
      toast.success("Answering settings saved. New questions use them right away.");
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  const generator = system.data?.generator;
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>How answers are written</CardTitle>
            <CardDescription>Applies to every conversation and API call in this workspace.</CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Answer mode">
            {MODES.map((mode) => (
              <button
                key={mode.value}
                type="button"
                role="radio"
                aria-checked={settings.answer_mode === mode.value}
                disabled={!editable}
                onClick={() => set("answer_mode", mode.value)}
                className={cn(
                  "rounded-xl border p-4 text-left transition-colors disabled:cursor-not-allowed",
                  settings.answer_mode === mode.value ? "border-primary bg-accent/50 ring-1 ring-primary/30" : "border-border hover:bg-muted/50",
                )}
              >
                <span className="text-[13.5px] font-semibold">{mode.title}</span>
                <span className="mt-1 block text-[12.5px] text-muted-foreground">{mode.text}</span>
              </button>
            ))}
          </div>
          <div className="grid gap-5 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="top-k">Passages per answer</Label>
              <NativeSelect id="top-k" value={settings.top_k} disabled={!editable} onChange={(e) => set("top_k", Number(e.target.value))}>
                {[3, 4, 6, 8, 10, 12].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="budget">Context budget</Label>
              <NativeSelect
                id="budget"
                value={settings.context_token_budget ?? ""}
                disabled={!editable}
                onChange={(e) => set("context_token_budget", e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Deployment default</option>
                {[1000, 1800, 3000, 6000, 12000].map((n) => (
                  <option key={n} value={n}>
                    {n.toLocaleString()} tokens
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="chunks">Passage size</Label>
              <NativeSelect
                id="chunks"
                value={settings.chunk_tokens ?? ""}
                disabled={!editable}
                onChange={(e) => set("chunk_tokens", e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">Deployment default</option>
                {[200, 320, 500, 800].map((n) => (
                  <option key={n} value={n}>
                    {n} tokens
                  </option>
                ))}
              </NativeSelect>
              <FieldHint>Applies to new uploads; reprocess older files to apply it.</FieldHint>
            </div>
          </div>
          <div className="flex items-center justify-between gap-4 rounded-xl border border-border px-4 py-3">
            <div>
              <Label htmlFor="cache">Answer cache</Label>
              <FieldHint>Reuse answers for the same or a near-identical question until the documents change.</FieldHint>
            </div>
            <Switch id="cache" checked={settings.cache_enabled} disabled={!editable} onCheckedChange={(v) => set("cache_enabled", v)} />
          </div>
          {editable ? (
            <Button onClick={save} disabled={update.isPending}>
              Save answering settings
            </Button>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>This deployment</CardTitle>
            <CardDescription>Configured by the operator through environment variables.</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-4 text-[13px] sm:grid-cols-3">
            <div className="space-y-0.5">
              <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Cpu className="size-3.5 text-primary" aria-hidden /> Answer model
              </dt>
              <dd className="font-medium">{generator ? (generator.uses_model ? `${generator.provider} / ${generator.model}` : "Local extractive (no model)") : "..."}</dd>
            </div>
            <div className="space-y-0.5">
              <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ScanSearch className="size-3.5 text-primary" aria-hidden /> Embeddings
              </dt>
              <dd className="font-medium">{system.data ? `${system.data.embeddings} (${system.data.embedding_dim}d)` : "..."}</dd>
            </div>
            <div className="space-y-0.5">
              <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Database className="size-3.5 text-primary" aria-hidden /> Tokenizer
              </dt>
              <dd className="font-medium">{system.data?.tokenizer ?? "..."}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

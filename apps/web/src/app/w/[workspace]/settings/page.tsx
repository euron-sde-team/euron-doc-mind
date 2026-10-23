"use client";

import { useParams } from "next/navigation";

import { ActivityPanel } from "@/components/settings/activity-panel";
import { AnsweringPanel } from "@/components/settings/answering-panel";
import { ApiKeysPanel } from "@/components/settings/api-keys-panel";
import { GeneralPanel } from "@/components/settings/general-panel";
import { MembersPanel } from "@/components/settings/members-panel";
import { ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkspace } from "@/lib/queries";

export default function SettingsPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const query = useWorkspace(workspace);
  const data = query.data;
  const owner = data?.role === "owner";

  return (
    <PageBody className="max-w-4xl">
      <PageHeader title="Settings" description="Workspace details, answering, people and programmatic access." />
      {query.error ? <ErrorNotice message={query.error.message} /> : null}
      {!data ? (
        <Skeleton className="h-64" />
      ) : (
        <Tabs defaultValue="general">
          <TabsList>
            <TabsTrigger value="general">General</TabsTrigger>
            <TabsTrigger value="answering">Answering</TabsTrigger>
            <TabsTrigger value="members">Members</TabsTrigger>
            {owner ? <TabsTrigger value="api-keys">API keys</TabsTrigger> : null}
            {owner ? <TabsTrigger value="activity">Activity</TabsTrigger> : null}
          </TabsList>
          <TabsContent value="general">
            <GeneralPanel key={data.corpus_version + data.name} workspace={data} editable={owner} />
          </TabsContent>
          <TabsContent value="answering">
            <AnsweringPanel workspace={data} editable={owner} />
          </TabsContent>
          <TabsContent value="members">
            <MembersPanel workspace={data.slug} isOwner={owner} />
          </TabsContent>
          {owner ? (
            <TabsContent value="api-keys">
              <ApiKeysPanel workspace={data.slug} />
            </TabsContent>
          ) : null}
          {owner ? (
            <TabsContent value="activity">
              <ActivityPanel workspace={data.slug} />
            </TabsContent>
          ) : null}
        </Tabs>
      )}
    </PageBody>
  );
}

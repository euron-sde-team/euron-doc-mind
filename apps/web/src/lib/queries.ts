"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ws } from "@/lib/api";
import type {
  ApiKey,
  ApiKeyCreated,
  AuditEvent,
  Conversation,
  DocumentDetail,
  DocumentPage,
  Insights,
  LibraryStats,
  Me,
  Member,
  Message,
  Role,
  SearchResult,
  SystemInfo,
  UploadResult,
  User,
  Workspace,
  WorkspaceSettings,
} from "@/lib/types";

export const qk = {
  system: ["system"] as const,
  me: ["me"] as const,
  workspace: (w: string) => ["workspace", w] as const,
  documents: (w: string, filters: DocumentFilters) => ["documents", w, filters] as const,
  documentsAll: (w: string) => ["documents", w] as const,
  stats: (w: string) => ["stats", w] as const,
  document: (w: string, id: string) => ["document", w, id] as const,
  conversations: (w: string) => ["conversations", w] as const,
  messages: (w: string, id: string) => ["messages", w, id] as const,
  insights: (w: string, days: number) => ["insights", w, days] as const,
  members: (w: string) => ["members", w] as const,
  apiKeys: (w: string) => ["api-keys", w] as const,
  audit: (w: string) => ["audit", w] as const,
};

export type DocumentFilters = { status?: string; kind?: string; q?: string };

export function useSystemInfo() {
  return useQuery({ queryKey: qk.system, queryFn: () => api<SystemInfo>("/api/v1/system/info"), staleTime: 300_000 });
}

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => api<Me>("/api/v1/auth/me"), retry: false });
}

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<{ user: User }>("/api/v1/auth/login", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useSignup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; name: string; password: string }) =>
      api<{ user: User }>("/api/v1/auth/signup", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/api/v1/auth/logout", { method: "POST" }),
    onSettled: () => client.clear(),
  });
}

export function useWorkspace(workspace: string) {
  return useQuery({ queryKey: qk.workspace(workspace), queryFn: () => api<Workspace>(ws(workspace)) });
}

export function useCreateWorkspace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      api<Workspace>("/api/v1/workspaces", { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.me }),
  });
}

export function useUpdateWorkspace(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name?: string; description?: string; settings?: WorkspaceSettings }) =>
      api<Workspace>(ws(workspace), { method: "PATCH", json: body }),
    onSuccess: (updated) => {
      client.setQueryData(qk.workspace(workspace), updated);
      void client.invalidateQueries({ queryKey: qk.me });
    },
  });
}

export function useDocuments(workspace: string, filters: DocumentFilters) {
  const params = new URLSearchParams({ limit: "100" });
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  return useQuery({
    queryKey: qk.documents(workspace, filters),
    queryFn: () => api<DocumentPage>(`${ws(workspace)}/documents?${params}`),
    // Poll only while something is still being indexed.
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.status === "queued" || d.status === "processing") ? 2000 : false,
  });
}

export function useLibraryStats(workspace: string) {
  return useQuery({
    queryKey: qk.stats(workspace),
    queryFn: () => api<LibraryStats>(`${ws(workspace)}/documents/stats`),
    refetchInterval: (query) => ((query.state.data?.processing ?? 0) > 0 ? 2000 : false),
  });
}

export function useDocument(workspace: string, id: string) {
  return useQuery({
    queryKey: qk.document(workspace, id),
    queryFn: () => api<DocumentDetail>(`${ws(workspace)}/documents/${id}`),
  });
}

export function useUpload(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData();
      for (const file of files) form.append("files", file, file.name);
      return api<UploadResult>(`${ws(workspace)}/documents`, { method: "POST", body: form });
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: qk.documentsAll(workspace) });
      void client.invalidateQueries({ queryKey: qk.stats(workspace) });
    },
  });
}

export function useDocumentAction(workspace: string) {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: qk.documentsAll(workspace) });
    void client.invalidateQueries({ queryKey: qk.stats(workspace) });
  };
  return {
    rename: useMutation({
      mutationFn: ({ id, title }: { id: string; title: string }) =>
        api(`${ws(workspace)}/documents/${id}`, { method: "PATCH", json: { title } }),
      onSuccess: refresh,
    }),
    reprocess: useMutation({
      mutationFn: (id: string) => api(`${ws(workspace)}/documents/${id}/reprocess`, { method: "POST" }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api<void>(`${ws(workspace)}/documents/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useConversations(workspace: string) {
  return useQuery({
    queryKey: qk.conversations(workspace),
    queryFn: () => api<Conversation[]>(`${ws(workspace)}/conversations?limit=50`),
  });
}

export function useMessages(workspace: string, conversationId: string | null) {
  return useQuery({
    queryKey: qk.messages(workspace, conversationId ?? "none"),
    queryFn: () => api<Message[]>(`${ws(workspace)}/conversations/${conversationId}/messages`),
    enabled: Boolean(conversationId),
  });
}

export function useCreateConversation(workspace: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { title?: string; document_ids?: string[] | null }) =>
      api<Conversation>(`${ws(workspace)}/conversations`, { method: "POST", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.conversations(workspace) }),
  });
}

export function useConversationActions(workspace: string) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: qk.conversations(workspace) });
  return {
    rename: useMutation({
      mutationFn: ({ id, title }: { id: string; title: string }) =>
        api(`${ws(workspace)}/conversations/${id}`, { method: "PATCH", json: { title } }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api<void>(`${ws(workspace)}/conversations/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useSearch(workspace: string) {
  return useMutation({
    mutationFn: (body: { query: string; document_ids?: string[] | null; limit?: number }) =>
      api<SearchResult>(`${ws(workspace)}/search`, { method: "POST", json: body }),
  });
}

export function useInsights(workspace: string, days: number) {
  return useQuery({
    queryKey: qk.insights(workspace, days),
    queryFn: () => api<Insights>(`${ws(workspace)}/insights?days=${days}`),
  });
}

export function useMembers(workspace: string) {
  return useQuery({ queryKey: qk.members(workspace), queryFn: () => api<Member[]>(`${ws(workspace)}/members`) });
}

export function useMemberActions(workspace: string) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: qk.members(workspace) });
  return {
    add: useMutation({
      mutationFn: (body: { email: string; name?: string; role: Role }) =>
        api<{ member: Member; temporary_password: string | null }>(`${ws(workspace)}/members`, {
          method: "POST",
          json: body,
        }),
      onSuccess: refresh,
    }),
    changeRole: useMutation({
      mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
        api<Member>(`${ws(workspace)}/members/${userId}`, { method: "PATCH", json: { role } }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (userId: string) => api<void>(`${ws(workspace)}/members/${userId}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useApiKeys(workspace: string, enabled = true) {
  return useQuery({
    queryKey: qk.apiKeys(workspace),
    queryFn: () => api<ApiKey[]>(`${ws(workspace)}/api-keys`),
    enabled,
  });
}

export function useApiKeyActions(workspace: string) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: qk.apiKeys(workspace) });
  return {
    create: useMutation({
      mutationFn: (body: { name: string; role: "viewer" | "editor"; expires_in_days: number | null }) =>
        api<ApiKeyCreated>(`${ws(workspace)}/api-keys`, { method: "POST", json: body }),
      onSuccess: refresh,
    }),
    revoke: useMutation({
      mutationFn: (id: string) => api<void>(`${ws(workspace)}/api-keys/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}

export function useAudit(workspace: string, enabled = true) {
  return useQuery({
    queryKey: qk.audit(workspace),
    queryFn: () => api<AuditEvent[]>(`${ws(workspace)}/audit?limit=100`),
    enabled,
  });
}

/** The signed-in user's summary of a workspace (including their role), from the session cache. */
export function useCurrentWorkspace(workspace: string) {
  const me = useMe();
  return me.data?.workspaces.find((w) => w.slug === workspace || w.id === workspace);
}

export function canEdit(role: Role | undefined): boolean {
  return role === "owner" || role === "editor";
}

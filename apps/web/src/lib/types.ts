/** API shapes, mirroring apps/api/src/docmind/schemas. */

export type Role = "owner" | "editor" | "viewer";
export type DocumentStatus = "queued" | "processing" | "ready" | "failed";
export type DocumentKind = "pdf" | "docx" | "xlsx" | "csv" | "pptx" | "txt" | "md" | "html";

export type User = {
  id: string;
  email: string;
  name: string;
  is_admin: boolean;
  created_at: string;
  last_login_at: string | null;
};

export type WorkspaceSummary = {
  id: string;
  slug: string;
  name: string;
  role: Role;
  document_count: number;
  member_count: number;
};

export type Me = { user: User; workspaces: WorkspaceSummary[] };

export type WorkspaceSettings = {
  answer_mode: "auto" | "extractive";
  top_k: number;
  context_token_budget: number | null;
  chunk_tokens: number | null;
  chunk_overlap_tokens: number | null;
  cache_enabled: boolean;
};

export type Workspace = {
  id: string;
  slug: string;
  name: string;
  description: string;
  settings: WorkspaceSettings;
  corpus_version: number;
  role: Role;
  created_at: string;
};

export type Member = {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  joined_at: string;
};

export type DocumentItem = {
  id: string;
  title: string;
  filename: string;
  kind: DocumentKind;
  mime_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  warnings: string[];
  section_count: number;
  chunk_count: number;
  token_count: number;
  attempts: number;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
};

export type DocumentPage = { items: DocumentItem[]; total: number; limit: number; offset: number };

export type Section = {
  ordinal: number;
  kind: "page" | "slide" | "sheet" | "section";
  label: string;
  text: string;
  token_count: number;
};

export type DocumentDetail = DocumentItem & { sections: Section[] };

export type LibraryStats = {
  documents: number;
  ready: number;
  processing: number;
  failed: number;
  chunks: number;
  tokens: number;
  bytes: number;
};

export type UploadResult = {
  created: DocumentItem[];
  duplicates: DocumentItem[];
  rejected: { filename: string; code: string; message: string }[];
};

export type Source = {
  n: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  location: string;
  heading: string;
  section_ordinal: number;
  char_start: number;
  char_end: number;
  snippet: string;
  score: number;
  vector_score: number | null;
  keyword_score: number | null;
};

export type Citation = {
  n: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  location: string;
  section_ordinal: number;
  char_start: number;
  char_end: number;
  quote: string;
};

export type Usage = {
  generator: string;
  cache: "miss" | "exact" | "semantic";
  context_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  baseline_tokens: number;
  saved_tokens: number;
  saved_ratio: number;
  latency_ms: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  sources: Source[];
  usage: Usage | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string;
  document_ids: string[] | null;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type SearchHit = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  location: string;
  heading: string;
  section_ordinal: number;
  char_start: number;
  char_end: number;
  snippet: string;
  score: number;
  vector_score: number | null;
  keyword_score: number | null;
};

export type SearchResult = { query: string; hits: SearchHit[]; took_ms: number };

export type Insights = {
  days: number;
  totals: {
    questions: number;
    searches: number;
    context_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    baseline_tokens: number;
    saved_tokens: number;
    saved_ratio: number;
    cache_hits: number;
    cache_hit_rate: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
  };
  daily: {
    day: string;
    questions: number;
    context_tokens: number;
    baseline_tokens: number;
    saved_tokens: number;
    cache_hits: number;
  }[];
  top_documents: { document_id: string; title: string; citations: number }[];
  library: LibraryStats;
  generator: string;
  embeddings: string;
};

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  role: "viewer" | "editor";
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type ApiKeyCreated = ApiKey & { key: string };

export type AuditEvent = {
  id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  actor_name: string | null;
  created_at: string;
};

export type SystemInfo = {
  product_name: string;
  version: string;
  generator: { label: string; provider: string; model: string | null; uses_model: boolean };
  embeddings: string;
  embedding_dim: number;
  tokenizer: string;
  max_upload_mb: number;
  accepted_extensions: string[];
  allow_signup: boolean;
  needs_setup: boolean;
};

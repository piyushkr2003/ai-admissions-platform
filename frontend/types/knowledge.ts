export type KnowledgeSourceStatus = "uploaded" | "queued" | "processing" | "ready" | "failed" | "archived";
export type KnowledgeSourceType = "pdf" | "docx" | "txt" | "csv" | "xlsx" | "website" | "faq" | "manual";
export type KnowledgeVisibility = "public" | "internal";

export type KnowledgeSource = {
  id: string;
  college_id: string;
  name: string;
  source_type: KnowledgeSourceType | string;
  status: KnowledgeSourceStatus | string;
  version: number;
  visibility: KnowledgeVisibility | string;
  content_hash: string | null;
  embedding_model: string | null;
  error_message: string | null;
  last_synced_at: string | null;
  created_at: string;
};

export type KnowledgeSourceCreate = {
  name: string;
  source_type: string;
  text?: string;
  file_base64?: string;
  visibility?: KnowledgeVisibility;
  effective_from?: string;
  effective_until?: string;
};

export type KnowledgeSearchResult = {
  chunk_id: string;
  source_id: string;
  title: string | null;
  content: string;
  score: number;
};

export type KnowledgeSearchResponse = {
  results: KnowledgeSearchResult[];
  has_reliable_evidence: boolean;
};

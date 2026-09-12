"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextInput } from "@/components/ui/form";
import { EmptyState } from "@/components/ui/state";
import { useAuth } from "@/features/auth/auth-provider";
import { useTenant } from "@/features/tenant/tenant-provider";
import { ApiError } from "@/lib/api/client";
import { knowledgeApi } from "@/lib/api/knowledge";
import type { KnowledgeSearchResponse } from "@/types/knowledge";

export function KnowledgeSearchPanel() {
  const { apiClient } = useAuth();
  const { collegeId } = useTenant();
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<KnowledgeSearchResponse | null>(null);

  async function handleSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await knowledgeApi.search(apiClient, collegeId, query);
      setResult(response.data);
    } catch (searchError) {
      setError(searchError instanceof ApiError ? searchError.message : "Search failed.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card subtitle="Runs the same retrieval the AI agent uses, scoped to this college's knowledge base." title="Test Retrieval">
      <form className="toolbar" onSubmit={handleSearch}>
        <TextInput
          aria-label="Search knowledge base"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. What is the application deadline?"
          value={query}
        />
        <Button disabled={busy} icon={<Search size={16} aria-hidden="true" />} type="submit">
          Search
        </Button>
      </form>
      {error ? <p className="form-field__error">{error}</p> : null}
      {result ? (
        <div className="detail-section">
          <Badge tone={result.has_reliable_evidence ? "success" : "warning"}>
            {result.has_reliable_evidence ? "Reliable evidence found" : "No reliable evidence"}
          </Badge>
          {result.results.length === 0 ? (
            <EmptyState title="No matching chunks found" />
          ) : (
            result.results.map((chunk) => (
              <div className="checklist__item" key={chunk.chunk_id}>
                <div>
                  <strong>{chunk.title ?? "Untitled source"}</strong>
                  <span>{chunk.content}</span>
                </div>
                <Badge tone="info">{chunk.score.toFixed(2)}</Badge>
              </div>
            ))
          )}
        </div>
      ) : null}
    </Card>
  );
}

"""Tool: search_knowledge (docs/agent-tools.md section 10).

The agent always searches with include_internal=False - prospective
students must never receive internal-only knowledge, regardless of
what they ask.
"""
from __future__ import annotations

from app.agent.schemas import ToolResult
from app.agent.tools.base import ToolContext
from app.rag.retrieval.service import RetrievalService


def search_knowledge(ctx: ToolContext, *, query: str, top_k: int | None = None) -> ToolResult:
    service = RetrievalService(ctx.db)
    result = service.search(college_id=ctx.college_id, query=query, top_k=top_k, include_internal=False)

    if not result.has_reliable_evidence:
        return ToolResult.fail("KNOWLEDGE_NOT_FOUND", "No reliable evidence was found for this question.")

    return ToolResult.ok({
        "results": [
            {
                "source_id": r.source_id,
                "title": r.title,
                "content": r.content,
                "score": r.score,
            }
            for r in result.results
        ]
    })

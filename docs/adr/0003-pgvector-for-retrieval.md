# 0003. Store embeddings in Postgres with pgvector

- **Status:** Accepted
- **Date:** 2026-10-02
- **Iteration:** −1

## Context

RAG covers a small corpus: 3 counterparties × (1 agreement + 2 amendments), a few hundred chunks. Retrieval must filter by `counterparty_id` and by effective date ("clause in force on date X"), and the plan uses hybrid search (vector + full text, fused with RRF). All other application data, LangGraph checkpoints, and the audit log already live in Postgres.

## Decision

Store chunk embeddings in Postgres with the `pgvector` extension, next to a `tsvector` column for full-text search. Metadata filters (`counterparty_id`, `effective_date`, `supersedes`) are plain SQL in the same query. Hosted on Neon in production.

## Alternatives considered

| Option | Why not |
|---|---|
| Pinecone / Weaviate / Qdrant | A second datastore to run and keep consistent; no benefit at this corpus size. |
| In-memory FAISS | No persistence or SQL filtering; rebuilt on every start. |
| Long context, no retrieval | Kept as an experiment row in the Iteration 4 table, not as the architecture. |

## Consequences

- **Positive:** one database, transactional writes, effective-date filtering and hybrid search in one SQL query.
- **Negative / cost:** fewer tuning knobs than a dedicated vector DB; index choice (HNSW vs IVFFlat) is ours to manage.
- **Follow-up:** the Iteration 4 experiment table decides whether reranking is worth its latency and cost.

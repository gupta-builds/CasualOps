# HiveMind — Claude Code Project Instructions

## What This Project Is

HiveMind is an evidence-backed causal reasoning engine for cyber SOC operations. The core design principle: **the LLM proposes hypotheses, deterministic code falsifies them**. The LLM designs a causal DAG. A separate evidence compiler ingests real SIEM/CVE/incident data, gates it statistically, and only then runs DoWhy estimation. If evidence is too weak, ATE is withheld. This is not a bug — it is the point.

## The Task in Progress

Implementing the **Persistent Semantic Memory and Retrieval Layer** from the roadmap.

Five components:
1. **Vector store** — every completed run is embedded (`text-embedding-3-small` via Azure) and stored in Supabase pgvector. New incidents retrieve the 3 most similar past runs before the orchestrator decomposes them.
2. **Knowledge graph** — entities (assets, MITRE techniques, CVEs, graph nodes) extracted from evidence records and causal graphs are persisted as nodes and edges across runs.
3. **Temporal indexing** — cosine similarity is multiplied by `exp(-0.023 * age_in_days)` (30-day half-life decay).
4. **MCP server** — FastMCP instance mounted at `/mcp` on the FastAPI app: `search_similar_incidents`, `get_entity_relationships`, `get_asset_timeline`, `write_run_to_memory`.
5. **Agent integration** — `memory_retrieve` node before orchestrator, `memory_write` node after DoWhy, orchestrator prompt extended with past context.

**Status:** Awaiting Azure embedding deployment + Supabase service role key. Do NOT write implementation code until credentials are confirmed in `.env`.

## Repository Structure

```
src/
  schema.py           ← All Pydantic models + GraphState TypedDict (THE contract)
  graph.py            ← LangGraph StateGraph assembly
  agents.py           ← Orchestrator, parent, child agent nodes
  evaluator.py        ← Memo ranking node
  causal.py           ← Causal synthesis + DoWhy engine nodes
  dataset_compiler.py ← Evidence → DataFrame compiler  !! DO NOT TOUCH !!
  estimators.py       ← DoWhy + statsmodels            !! DO NOT TOUCH !!
  evidence_adapters.py← SIEM/CVE/incident normalization
  benchmarking.py     ← Deterministic tier scoring
  engine.py           ← run_hivemind() + artifact persistence
  api.py              ← FastAPI: /run /estimate /demo/estimate normalizers
  demo_fixtures.py    ← Deterministic smoke-test evidence
  main.py             ← Legacy Streamlit UI
  memory/             ← NEW — entire memory layer
    __init__.py
    embedder.py       ← embed_text(str) -> list[float]  Azure text-embedding-3-small
    extractor.py      ← Deterministic entity extraction from run artifacts
    store.py          ← SupabaseMemoryStore (4 methods)
    nodes.py          ← memory_retrieve_node, memory_write_node
    mcp_server.py     ← FastMCP instance + 4 tools, mounted in api.py

app/src/integrations/supabase/
  client.ts           ← Supabase JS client (frontend, anon key)
  types.ts            ← Auto-generated — regenerate after schema changes
```

## Environment Variables

```bash
# Existing
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# New (needed before implementing memory layer)
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

# Supabase — client (VITE_ prefix, safe in browser)
VITE_SUPABASE_URL=https://lejmpbxchamaqjfclfyz.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=       # anon/public key
VITE_SUPABASE_PROJECT_ID=lejmpbxchamaqjfclfyz

# Supabase — server (secrets)
SUPABASE_URL=https://lejmpbxchamaqjfclfyz.supabase.co
SUPABASE_PUBLISHABLE_KEY=            # same anon key (auth middleware)
SUPABASE_SERVICE_ROLE_KEY=           # service_role key — NOT anon key
```

## Python Conventions

- Python 3.12. Pydantic v2. `from __future__ import annotations` on every new file.
- LangGraph nodes return **only changed fields** as a dict. LangGraph merges.
- `asyncio.to_thread()` wraps all blocking I/O (Supabase client, embedding API).
- Type hints everywhere. No bare `Any` unless unavoidable.
- Ruff (linting) + Pyright (types). Line length 88.

## Critical Rules

1. **Never pass memory retrieval results as `EvidenceRecord` objects.** Memory context goes into the orchestrator prompt only — not the evidence pipeline.
2. **Never let the LLM generate data rows.** The `source_type: "synthetic"` guard in `dataset_compiler.py` exists for this reason. Do not route around it.
3. **Never use the Supabase anon key in Python backend.** It will fail silently on writes due to RLS. Always use `SUPABASE_SERVICE_ROLE_KEY`.
4. **Never modify `dataset_compiler.py` or `estimators.py`** as part of the memory work. They are the core statistical safeguards.
5. **Never call `embed_text()` directly in async context** — always use `await asyncio.to_thread(embed_text, text)`.
6. **Never commit `.env` or `settings.local.json`.**

## How to Run

```bash
# Full stack
docker-compose up --build

# Backend only (from src/)
cd src && uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Smoke test (zero LLM tokens)
curl http://localhost:8000/demo/estimate

# Health check
curl http://localhost:8000/health

# MCP server (after implementation)
curl http://localhost:8000/mcp
```

## Supabase Schema (after migration)

Project ID: `lejmpbxchamaqjfclfyz`

Tables: `memory_runs`, `memory_entities`, `memory_entity_edges`
RPC functions: `search_similar_runs(query_embedding, match_count, decay_lambda)`, `get_entity_neighborhood(p_entity_value, p_entity_type)`

Regenerate TypeScript types after schema changes:
```bash
npx supabase gen types typescript \
  --project-id lejmpbxchamaqjfclfyz \
  --schema public \
  > app/src/integrations/supabase/types.ts
```

## LangGraph Graph Topology (post-implementation)

```
START → memory_retrieve → orchestrator → [parallel parent_agents]
      → gather_children → [parallel child_agents] → evaluate_memos
      → causal_synthesis → dowhy_engine
      → (retry → causal_synthesis | end → memory_write) → END
```

## New Packages Required

```
supabase==2.15.2
openai==1.91.0
fastmcp==3.2.4
httpx==0.28.1
```

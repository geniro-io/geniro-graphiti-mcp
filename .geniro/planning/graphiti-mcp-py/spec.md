---
tier: T1.5
producer: plan
schema-version: 1
branch: claude/geniro-fork-dynamic-workflows-criwgf
timestamp: 2026-06-27T21:06:35Z
geniro_kind: design-doc
geniro_schema_version: m5-v4
task_slug: graphiti-mcp-py
topic: "Clean-room Python rewrite of the Graphiti MCP server for the Claude CLI, embedding graphiti-core with synchronous writes over Neo4j."
mode: IDEA
effort_tier: medium
lifecycle: approved
budget:
  max_files_to_edit: null
  max_lines_changed: null
  time_budget: null
checkpoints:
  - step_anchor: step-4
    name: "Engine connects to Neo4j + indices built"
  - step_anchor: step-9
    name: "All MCP tools registered"
  - step_anchor: step-12
    name: "Tests green (unit + testcontainers)"
forbidden_actions:
  - "do NOT reintroduce a background queue / async worker for add_memory — writes MUST be awaited synchronously so errors propagate (this is the whole point of the rewrite)"
  - "do NOT use OpenAIClient for an OpenAI-compatible/Ollama base_url — use OpenAIGenericClient, or the base_url is ignored (graphiti issue #1116) and writes 401 silently"
  - "do NOT commit API keys or .env — only .env.example with placeholders"
  - "do NOT default the embedder to a chat model — it MUST be an embedding model (qwen3-embedding:8b), with EMBEDDER_DIM matching the model"
approval_required_for:
  - step-12
tools_required: ["uv", "docker", "ollama"]
launch_config:
  workspace: current-branch
  deep_mode: false
  branch_freshness: skip
  ship_mode: commit-no-push
---

<!-- geniro:design-doc -->

# Geniro Graphiti MCP — Python rewrite for the Claude CLI

## 1. Objective

Build a clean-room Python MCP server that embeds graphiti-core and writes to Neo4j synchronously, exposing Graphiti memory tools to the Claude CLI over stdio without the upstream silent-drop bug.

## 2. Scope — Included

- New Python package laid out under `src/graphiti_mcp/` (created from scratch — empty repo).
- `pyproject.toml` — uv + pip installable, Python 3.11, console script `graphiti-mcp`, deps: `graphiti-core` (with anthropic extra), `mcp` (FastMCP), `openai`, `pydantic`/`pydantic-settings`, dev: `pytest`, `pytest-asyncio`, `testcontainers[neo4j]`.
- `src/graphiti_mcp/config.py` — env/.env settings (Neo4j, LLM, embedder, group_id, semaphore).
- `src/graphiti_mcp/providers.py` — LLM + embedder factory (OpenAI `gpt-5.5` default / Anthropic / OpenAI-compatible base_url incl. LiteLLM & Ollama; embedder default Ollama `qwen3-embedding:8b` dim 4096).
- `src/graphiti_mcp/engine.py` — Graphiti(Neo4jDriver,…) lifecycle: build_indices_and_constraints on startup, close on shutdown.
- `src/graphiti_mcp/server.py` — FastMCP server, stdio transport, tool registration, entrypoint.
- `src/graphiti_mcp/tools/` — the ~13 MCP tools (ingest, search, episodes/edges, admin) mirroring upstream tool names.
- `src/graphiti_mcp/models.py` — pydantic request/response models + formatting.
- `docker-compose.yml` — Neo4j 5.26+ only (server runs on host via stdio).
- `.env.example`, `README.md`, `tests/**` (unit + testcontainers integration), `.github/workflows/ci.yml`.

## 3. Scope — Excluded

- JWT/bearer auth and group_id-from-token multi-tenant isolation — out of scope (these were hosted-product concerns; `group_id` stays only as an optional namespacing param).
- Redis / BullMQ / Postgres-outbox / any background-queue infrastructure — explicitly excluded; the rewrite is queue-free by design.
- HTTP / SSE transports — stdio only for v1 (the env-driven transport switch may be added later).
- FalkorDB backend — Neo4j only for v1.
- Any separate "graphiti REST service" (architecture B) — the engine is embedded in-process (architecture A).
- The Geniro plugin wiring (knowledge-retrieval / emit-learning integration) — a downstream consumer, not this repo.

## 4. Assumptions

- graphiti-core's current API matches the researched signatures (`add_episode(name, episode_body, source_description, reference_time, source, group_id, …)`, `search(query, group_ids, num_results)`, `build_indices_and_constraints()`, `close()`); pin the version and verify against the installed package at build time.
- Neo4j 5.26+ is reachable at `NEO4J_URI` (bundled docker-compose or BYO) with Bolt on 7687.
- For the default embedder, an Ollama daemon serving `qwen3-embedding:8b` is available at `EMBEDDER_BASE_URL` (default `http://localhost:11434/v1`); otherwise the user sets a cloud embedder.
- Docker is available for testcontainers-based integration tests.

## 5. Risks

- **medium — local extraction quality.** A local main LLM produces weaker entity extraction. *Mitigation:* default the main LLM to OpenAI `gpt-5.5` (not local); document the trade-off; keep providers env-switchable.
- **medium — embedder/dim mismatch silently breaks search.** Wrong `EMBEDDER_MODEL`/`EMBEDDER_DIM` (e.g. a chat model, or dim ≠ 4096 for qwen3-embedding:8b) yields empty/garbage search. *Mitigation:* validate dim at startup, log the resolved embedder, add a post-write read-back smoke test, document the requirement.
- **low — graphiti-core API drift.** Method signatures have churned upstream. *Mitigation:* pin the version; integration tests catch breakage.
- **low — `clear_graph` is destructive.** *Mitigation:* scope it to `group_id`, require explicit invocation; never run implicitly.

## 6. Steps

- [ ] 1. Scaffold the uv+pip project: `pyproject.toml:1` (deps, console script `graphiti-mcp`), `.python-version:1` (3.11), `README.md:1`, `.env.example:1`, `.gitignore:1`. <!-- step-1 -->
- [ ] 2. Implement `src/graphiti_mcp/config.py:1` — pydantic-settings `Settings` reading `NEO4J_URI/USER/PASSWORD/DATABASE`, `LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL`, `EMBEDDER_PROVIDER/EMBEDDER_MODEL/EMBEDDER_DIM/EMBEDDER_BASE_URL`, `GRAPHITI_GROUP_ID` (default `main`), `SEMAPHORE_LIMIT`. <!-- step-2 -->
- [ ] 3. Implement `src/graphiti_mcp/providers.py:1` — `build_llm_client()` (OpenAIClient `gpt-5.5` / AnthropicClient / OpenAIGenericClient+base_url for LiteLLM/Ollama) and `build_embedder()` (OpenAIEmbedder default Ollama `qwen3-embedding:8b` dim 4096 / openai / voyage); never OpenAIClient for base_url (#1116). <!-- step-3 -->
- [ ] 4. Implement `src/graphiti_mcp/engine.py:1` — construct `Graphiti(graph_driver=Neo4jDriver(...), llm_client=..., embedder=...)`; `build_indices_and_constraints()` at startup; `close()` at shutdown; expose a singleton accessor. <!-- step-4 -->
- [ ] 5. Implement `src/graphiti_mcp/server.py:1` — `FastMCP("graphiti")`, stdio transport, startup/shutdown lifecycle wiring, register all tools, `main()` entrypoint for the console script. <!-- step-5 -->
- [ ] 6. Implement ingest tools in `src/graphiti_mcp/tools/episodes.py:1` — `add_memory` that AWAITS `graphiti.add_episode(...)` and returns the real success/error (no enqueue-and-return), plus `add_triplet`. Map `EpisodeType` (message/text/json). <!-- step-6 -->
- [ ] 7. Implement search tools in `src/graphiti_mcp/tools/search.py:1` — `search_nodes` (structured `search_`/SearchResults → nodes) and `search_memory_facts` (`search(...)` → edges, return `.fact`). <!-- step-7 -->
- [ ] 8. Implement retrieval/deletion tools in `src/graphiti_mcp/tools/graph.py:1` — `get_episodes`, `get_episode_entities`, `get_entity_edge`, `delete_entity_edge`, `delete_episode`. <!-- step-8 -->
- [ ] 9. Implement admin tools in `src/graphiti_mcp/tools/admin.py:1` — `build_communities`, `summarize_saga`, `clear_graph` (group-scoped, guarded), `get_status` (Neo4j connectivity + resolved provider/embedder/dim — NOT queue depth). <!-- step-9 -->
- [ ] 10. Implement `src/graphiti_mcp/models.py:1` — pydantic request/response + `SuccessResponse`/`ErrorResponse`/`StatusResponse` and node/fact formatting helpers mirroring upstream `response_types`. <!-- step-10 -->
- [ ] 11. Add `docker-compose.yml:1` (neo4j:5.26, ports 7474/7687, healthcheck, volume) and finalize `.env.example:1` + `README.md:1` install/run docs (`uv run`/`pipx`, `claude mcp add graphiti-mcp -- graphiti-mcp`). <!-- step-11 -->
- [ ] 12. Tests: `tests/unit/` mock graphiti-core to assert tool logic + that a write failure propagates as an MCP error (no silent drop); `tests/integration/test_roundtrip.py` uses `testcontainers[neo4j]` for a real add_memory→search round-trip + post-write read-back smoke test. <!-- step-12 -->
- [ ] 13. Add `.github/workflows/ci.yml:1` — run `uv run pytest` (unit always; integration gated on Docker availability). <!-- step-13 -->

## 7. Tools Required

- `uv` — project/dependency management and run (`uv run graphiti-mcp`); pip/pipx also supported.
- `docker` — run bundled Neo4j via docker-compose and spin testcontainers Neo4j in integration tests.
- `ollama` — serve the default embedder `qwen3-embedding:8b` (optional if a cloud embedder is configured instead).

## 8. Approval Points

- step-12 — review the test strategy/coverage (unit error-propagation + testcontainers round-trip) before finalizing, since "no silent drops, with tests" is the core acceptance criterion.

## 9. Validation

- **Unit (mocked):** graphiti-core mocked; assert each tool calls the engine with correct args, and that an exception from `add_episode` surfaces as an MCP `ErrorResponse` rather than a success (the anti-silent-drop guarantee). `verify: uv run pytest tests/unit -q`
- **Integration (testcontainers, real Neo4j):** start a Neo4j container; run `add_memory` then `search_memory_facts` and assert the ingested fact is returned; run a post-write Cypher node-count read-back to confirm the graph is non-empty.
- **Manual (Claude CLI):** `claude mcp add graphiti-mcp -- graphiti-mcp`, call `add_memory`, then `search_memory_facts`, and confirm the fact comes back and `get_status` reports a healthy Neo4j connection and the resolved providers.

## 10. Rollback-Recovery

Pure additive — the repository is empty (greenfield), so recovery is `git revert`/branch-delete with no data migration and no downstream coupling. The bundled Neo4j is disposable (drop the docker volume to reset). No rollback of external state is required.

## 11. Done Condition

All unit and testcontainers integration tests pass AND `claude mcp add graphiti-mcp` followed by `add_memory`→`search_memory_facts` returns the ingested fact (graph non-empty), AND a misconfigured embedder/LLM makes `add_memory` return a synchronous MCP error instead of a false success.

## Considered Alternatives

### Architecture B — MCP as a thin client to a separate graphiti REST service (rejected)
Run graphiti's `graph_service` container (providers configured there) and have the MCP call it over HTTP. Trade-off: configuration lives in one external service, but it adds a network hop, more moving parts, and reintroduces the upstream async-202 durability bug the rewrite exists to remove. Rejected in favor of architecture A (embed graphiti-core in-process) per user decision.

### TypeScript wrapper (original design-doc recommendation, rejected)
The source design doc recommended a TypeScript MCP wrapper over Python graphiti-core as a black box. Rejected because the user chose Python — which removes the cross-language boundary entirely (graphiti-core is Python), making a direct in-process wrapper strictly simpler.

### Durable queue (Redis/BullMQ/outbox, rejected)
Keep an async ingestion queue but make it durable (Redis BRPOPLPUSH + DLQ, or a Postgres outbox). Trade-off: higher throughput and request/processing decoupling, but materially more code and ops surface, and it is the source of the silent-drop bug class. Rejected: synchronous awaited writes are the simplest correct design for a local single-user Claude-CLI MCP and eliminate the bug by construction.

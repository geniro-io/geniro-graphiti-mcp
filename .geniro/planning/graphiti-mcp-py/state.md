---
tier: T1.5
producer: plan
schema-version: 1
branch: claude/geniro-fork-dynamic-workflows-criwgf
worktree: /home/user/geniro-graphiti-mcp
timestamp: 2026-06-27T20:42:33Z
phase: done
status: in-progress
non-resumable-actions:
  - action: git-commit
    completed-at: 2026-06-27T21:09:10Z
    commit-sha: 33d36c2e00d4899ac5a32092dd49d9a7d5385a6f
    files: ['.geniro/planning/graphiti-mcp-py/spec.md']
approvals:
  - category: approach_choice
    picked: 'Architecture A — embed graphiti-core in-process (Python)'
    at: 2026-06-27T21:09:10Z
  - category: section_objective
    picked: approve
    at: 2026-06-27T21:09:10Z
  - category: final_approve
    picked: 'Approve — commit the plan'
    at: 2026-06-27T21:09:10Z
  - category: launch_config
    picked: 'current-branch / skip / commit-no-push / standard'
    at: 2026-06-27T21:09:10Z
task_slug: graphiti-mcp-py
mode: IDEA
deep-mode: false
---

# State: Geniro Graphiti MCP — fork from scratch (TS wrapper)

## Inputs
- Source design doc (remote): geniro-claude-harness/research/agent-memory-mcp/graphiti-fork-suggestion.md
- Sibling docs read: graphiti-integration-plan.md, graphiti-gotchas.md
- Directive: "create fork from scratch based on this. Use dynamic workflows everywhere you need."
- Repo: geniro-graphiti-mcp (empty greenfield, no commits)

## Prior Design Doc (synthesized)
- Recommended approach: thin TypeScript MCP wrapper over Python graphiti-core (black box) — NOT a python fork, NOT a TS reimplementation.
- Engine boundary: TS layer -> Python graphiti engine via REST (graph_service) or minimal Python ASGI shim.
- Auth: backend-issued Bearer JWT; derive group_id from JWT claims (never trust X-Group-Id header).
- Queue options ranked: (1) synchronous awaited write (plugin/low-volume), (2) BullMQ (Redis, retries+DLQ, dashboards), (3) Postgres outbox (max durability, DB is source of truth).
- MCP tools: add_episode, get_episode_status, get_queue_status, query_graph/search, clear_graph(per-group), list_group_ids.
- Transport: stdio first, HTTP for multi-tenant/remote.
- Graph store: FalkorDB (chosen in integration-plan for low ops overhead).
- Embedder MUST be provisioned (OpenAI or Ollama nomic-embed-text dim 768); await all writes; high max_tokens; beware #1116 OpenAI api_base fallback.
- Upstream bugs: #566 async_worker.start() never called -> silent 202 + empty graph; family #325/#450/#871/#1062/#1116/#1469.
- michabbb fork fixes: Redis BRPOPLPUSH durable queue + crash recovery + get_queue_status/list_group_ids + graceful shutdown + token auth; REMAINING GAP: fail(requeue=False) silently drops on processing error (no DLQ), single static query-param nonce, trusts X-Group-Id, zero tests.

## Tool log
- ts: 2026-06-27T20:42:33Z
  tool: WebFetch
  detail: "Fetched + extracted 3 design docs (fork-suggestion, integration-plan, gotchas)"
  status: ok
  summary: "TS-wrapper recommendation, FalkorDB store, queue options, MCP tool surface captured"

## Errors

## Open Questions

## Settled Decisions (pre-grill)
- LANGUAGE: Python (user directive "Let's use python", 2026-06-27) — OVERRIDES the design doc's TypeScript-wrapper recommendation.
  Consequence: no cross-language REST shim. Build a Python MCP server that imports graphiti-core directly and calls graphiti.add_episode()/search() in-process (synchronous awaited). This is exactly what gotchas.md recommends. The doc's anti-fork argument was largely "team uses TS"; with Python chosen, the natural fit is a thin Python MCP layer owning auth/queue/multi-tenancy over graphiti-core as a library black box.

## Scope Clarifications (user, 2026-06-27)
- PRODUCT NAME: "Geniro" (NOT "Genera" — the source docs misname it).
- DEPLOYMENT TARGET: a personal/local MCP server used with the Claude CLI (`claude mcp add`). NOT the hosted multi-tenant Genera product.
- CONSEQUENCES (scope reductions vs the design doc):
  * Transport = stdio (Claude Code's standard MCP transport). HTTP transport not required for v1.
  * DROP JWT bearer auth + group_id-from-token multi-tenant isolation — those were for the hosted product (Path A). A local single-user MCP needs no auth layer.
  * DROP BullMQ / Redis / Postgres-outbox queue infrastructure — synchronous awaited writes (graphiti.add_episode awaited in-process) are the right model and inherently fix the #566 / fail(requeue=False) silent-drop bugs.
  * group_id retained only as an OPTIONAL namespacing param (e.g. per-project memory), not a security boundary.
- Effort tier reassessed: Medium (was Big). Likely single spec, no milestone slicing.
- Still in scope: graphiti-core wrapped directly in Python, FalkorDB (vs Neo4j) backend, correct embedder config, MCP tool surface mirroring upstream getzep/graphiti where sensible, env-var config, and Claude-CLI install instructions.

## Settled Decision — Graph store (user, 2026-06-27)
- GRAPH STORE: Neo4j (NOT FalkorDB). Neo4j is graphiti-core's default/best-supported driver (Neo4jDriver, requires Neo4j 5.26+). Overrides the integration-plan's FalkorDB pick.

## Settled Decision — Goal & "fork from scratch" meaning (user, 2026-06-27)
- GOAL: a clean-room REWRITE of the initial/upstream graphiti MCP server (getzep/graphiti mcp_server), NOT a vendor/patch of existing code.
  Deliver: (1) clean, readable code; (2) a real TEST SUITE (upstream + all forks have zero tests); (3) NO silent-drop bug; (4) a CLEANER, EASIER queue solution.
- QUEUE DIRECTION: simplest-correct. Default = synchronous awaited writes (await graphiti.add_episode) — no background worker, no Redis, errors propagate to the caller. This is the "easier solution" and structurally eliminates the #566 / fail(requeue=False) drop bugs. (Confirm in grill whether any minimal in-process async is wanted; lean: no queue.)
- Mirror upstream tool surface/names where sensible for familiarity, but our own clean implementation.
- Tier confirmed: Medium, single spec.

## Source-grounded findings (downloaded upstream + fork, 2026-06-27T20:51:05Z)
- Upstream getzep/graphiti mcp_server uses FastMCP (mcp.server.fastmcp). Transports: stdio / http(streamable, default) / sse(deprecated).
- Upstream TOOL SURFACE (src/graphiti_mcp_server.py): add_memory, search_nodes, search_memory_facts, get_episodes, get_episode_entities, get_entity_edge, delete_entity_edge, delete_episode, add_triplet, build_communities, summarize_saga, clear_graph, get_status. Plus a status resource.
- Upstream QUEUE (src/services/queue_service.py): per-group_id in-memory asyncio.Queue + background worker. add_memory enqueues and RETURNS IMMEDIATELY ("processes in the background"). On processing error the worker only logs (silent drop); a process crash loses the whole in-memory queue. THIS is the durability bug class we remove by awaiting writes directly.
- Upstream PROVIDERS (src/config/schema.py, pydantic BaseSettings + YAML + env overrides): LLM = openai|azure|anthropic|gemini|groq; Embedder = openai|gemini|voyage (default text-embedding-3-small, 1536 dims); DB = neo4j|falkordb. Defaults: llm gpt-5.5, embedder text-embedding-3-small, db falkordb, group_id 'main', user_id 'mcp_user'.
- Fork michabbb adds Redis BRPOPLPUSH durable queue + auth(nonce) + group_id context; its queue/worker.py drops on processing error (fail(requeue=False) -> LREM, no DLQ). We avoid the entire queue layer, so this whole module class disappears.
- IMPLICATION for rewrite: keep add_memory's tool name/params but make it AWAIT graphiti.add_episode and return real success/failure. Drop queue_service entirely. get_status reports connectivity, not queue depth.

## Open decisions for grill (Phase 3)
1. LLM + embedder provider config (embedder is REQUIRED even w/ Anthropic LLM).
2. Tool surface scope for v1 (full upstream set vs lean core).
3. Config style: env-vars-only vs YAML+env (upstream uses YAML).
4. Test strategy: how Neo4j is provided in tests (mock graphiti / testcontainers / live).
5. Packaging/run for Claude CLI (uvx/pipx; Neo4j via docker-compose).

## Grill answers (2026-06-27T20:56:13Z)
- Tool surface = FULL UPSTREAM PARITY (all ~13 tools: add_memory, search_nodes, search_memory_facts, get_episodes, get_episode_entities, get_entity_edge, delete_entity_edge, delete_episode, add_triplet, build_communities, summarize_saga, clear_graph, get_status).
- Test strategy = TESTCONTAINERS integration (real Neo4j spun in tests) + unit tests.
- Provider config: user asked "why configure providers for mcp if graphiti server already configured?" -> surfaced architecture fork A vs B; resolving with a clarifying question. Pending.
- Packaging: user unsure -> recommending uv project + docker-compose Neo4j.
- Research workflow wyvfenj6q complete (5 facets+synthesis). Key reusable: graphiti-core API cheatsheet (add_episode kw signature, EpisodeType, search vs search_/SearchResults, OpenAIGenericClient vs OpenAIClient for #1116, build_indices_and_constraints, await-all, graphiti.close()). Output: tasks/wyvfenj6q.output. NOTE: use Neo4jDriver not FalkorDriver; ignore the synthesis's JWT/HTTP framing (dropped per local-CLI scope).

## Final settled design (2026-06-27T21:00:46Z)
- Architecture A: MCP embeds graphiti-core; builds Graphiti(Neo4jDriver,...) in-process; awaits add_episode/search; no queue; no separate graphiti server.
- TWO models (user-confirmed): main LLM (extraction) + embedder (vectors), independently env-configurable. Default both OpenAI (gpt-4.1-mini-ish + text-embedding-3-small 1536d); switchable LLM->Anthropic/Gemini/Groq, embedder->Voyage/Ollama(nomic-embed-text 768d). Use OpenAIGenericClient for OpenAI-compatible/Ollama base_url (avoids #1116).
- Neo4j: bundled minimal docker-compose.yml (neo4j:5.26+, 7474/7687) for one-command local DB; OR bring-your-own via NEO4J_URI/USER/PASSWORD/DATABASE env. MCP server runs on host (stdio), not containerized.
- Packaging: uv + pip. pyproject.toml, console_script entry 'graphiti-mcp', runnable via 'uvx'/'uv run' AND pip/pipx install. claude mcp add -> command = graphiti-mcp (stdio).
- Tools: FULL upstream parity (~13), our clean impl, add_memory awaits (synchronous).
- Tests: testcontainers (real Neo4j) integration + unit tests; pytest.
- Config: env vars / .env (pydantic-settings), no YAML layer.
- build_indices_and_constraints() at startup; graphiti.close() at shutdown.

## FINAL provider resolution (2026-06-27T21:04:40Z)
- Main LLM: default OpenAI gpt-5.5. Provider factory keyed by env LLM_PROVIDER:
  * openai (OpenAIClient, default model gpt-5.5)
  * anthropic (graphiti AnthropicClient, native Claude support)
  * openai_generic / openai-compatible (OpenAIGenericClient + LLM_BASE_URL) -> covers LiteLLM proxy (100+ providers) AND Ollama AND any compatible gateway.
  env: LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL, OPENAI_API_KEY/ANTHROPIC_API_KEY.
- Embedder: default Ollama qwen3-embedding:8b, EMBEDDER_DIM=4096, via OpenAIEmbedder(base_url=ollama). Switchable: openai (text-embedding-3-small,1536) | voyage | any openai-compatible base_url.
  env: EMBEDDER_PROVIDER, EMBEDDER_MODEL, EMBEDDER_DIM, EMBEDDER_BASE_URL.
- CAUTION baked into Risks: embedder model must be an EMBEDDING model (qwen3-embedding:* NOT qwen3:8b chat); EMBEDDER_DIM must match the model or search breaks; OpenAIGenericClient (not OpenAIClient) for base_url to avoid #1116.
- DESIGN FULLY SETTLED -> proceeding to author spec.md.

## Tool log (research + authoring)
- ts: 2026-06-27T21:07:22Z
  tool: Agent
  detail: "Research: upstream getzep/graphiti mcp_server tool surface + queue bug"
  status: ok
  summary: "13 tools, FastMCP, in-memory asyncio.Queue silent-drop confirmed"
  citations:
  - refs/graphiti-main/mcp_server/src/graphiti_mcp_server.py:341
  - refs/graphiti-main/mcp_server/src/services/queue_service.py:60
- ts: 2026-06-27T21:07:22Z
  tool: Agent
  detail: "Research: graphiti-core library API (add_episode/search/indices/providers)"
  status: ok
  summary: "kw signatures, EpisodeType, OpenAIGenericClient vs OpenAIClient #1116"
  citations:
  - refs/graphiti-main/graphiti_core/graphiti.py:1
- ts: 2026-06-27T21:07:22Z
  tool: Agent
  detail: "Research: michabbb fork structure + fail(requeue=False) drop bug"
  status: ok
  summary: "Redis queue + the no-DLQ drop; we drop the queue layer entirely"
  citations:
  - refs/graphiti-mcp-but-working-main/graphiti_mcp_server/queue/worker.py:1
- ts: 2026-06-27T21:07:22Z
  tool: Agent
  detail: "Research: MCP Python SDK / FastMCP transports + config"
  status: ok
  summary: "FastMCP stdio/http; pydantic tool IO"
  citations:
  - refs/graphiti-main/mcp_server/src/config/schema.py:76
- ts: 2026-06-27T21:07:22Z
  tool: atomic_state_write
  detail: ".geniro/planning/graphiti-mcp-py/spec.md"
  status: ok
  result_ref: "128 lines, 11 sections + Considered Alternatives"

## Validator result (Phase 7, orchestrator-side)
- single_objective: pass; bounded_scope: pass; source_materials: pass (>=4 Agent ok entries, Medium tier); allowed_tools: pass (sec7 <-> tools_required); forbidden_actions: pass; budget: pass; checkpoints: pass (3, >=5 steps); validation_method: pass; stopping_condition: pass; placeholder_scan: pass; contradiction_heuristic: pass; scope_creep_marker: pass (steps within src/graphiti_mcp/** + declared root files); schema_completeness: pass (11 + Considered Alternatives); workflow_refs_consistency: skip (m5-v1); launch_config_consistency: skip (absent). VALIDATOR CLEAN.

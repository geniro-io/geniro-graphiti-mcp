---
tier: T1.5
producer: plan
schema-version: 1
branch: claude/geniro-fork-dynamic-workflows-criwgf
worktree: /home/user/geniro-graphiti-mcp
timestamp: 2026-06-27T20:42:33Z
phase: explore
status: in-progress
non-resumable-actions: []
approvals: []
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

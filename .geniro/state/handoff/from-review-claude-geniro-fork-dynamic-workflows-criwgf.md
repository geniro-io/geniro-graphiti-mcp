---
tier: T2
producer: review
schema-version: 1
branch: claude/geniro-fork-dynamic-workflows-criwgf
timestamp: 2026-06-28T00:00:00Z
phase: action-gate
status: in-progress
report_status: final
pr-ref: none
risk-tier: standard
round: 1
reviewers_spawned: [bugs, security, architecture, tests, optimizations, code-quality, conventions, regressions, spec-compliance]
mechanical_prepass_attempted: [lint, schema, secret]
non-resumable-actions: []
approvals: []
open_questions: []
---

# Code Review — Geniro Graphiti MCP (clean-room implementation)

Scope: entire branch implementation (~1273 LOC source + tests). 9 reviewer dimensions,
each finding verified against the installed `graphiti-core` and the actual code.
**0 CRITICAL. 2 HIGH, 13 MEDIUM, ~20 LOW.** API surface verified non-hallucinated;
all 4 spec `forbidden_actions` honored; secret scan + ruff clean.

## Findings

### HIGH

- [ ] **H1 — `redact_secrets` leaks quoted `key: "value"` secrets (the dominant JSON/dict error-body shape)** `[FIX-NOW]`
  - File: `src/graphiti_mcp/errors.py:22-25` (pattern #3) + `_redact_kv` at `:43-47`
  - Decision Type: automatic-fix
  - Convergence: security (HIGH); independently reproduced by orchestrator.
  - Evidence (live repro): `redact_secrets('{"openai_api_key": "proxy-LEAKED1234567"}')` → returns the string UNCHANGED. Same for `{"password": "db-LEAKED-pw"}`, `{"secret": "..."}`, single-quoted dict reprs. The value-side class `[\"']?[^\s\"',)]+` consumes the opening quote then the negated class can't match the quoted body, so nothing is redacted. Plain `api_key=value` and `sk-...`/`Bearer ...` DO redact correctly — only the quoted-value form leaks.
  - Why it matters: LLM/HTTP/DB client exceptions are overwhelmingly JSON/dict reprs (`Error code: 401 - {'error': {...}}`, httpx bodies). Proxy keys (LiteLLM/OpenRouter/Ollama), Voyage keys, and Neo4j passwords frequently lack an `sk-`/`Bearer` prefix, so this is the redactor's primary intended catch — and it fails. This is the single genuinely-important defect in the review.
  - Suggested fix: make the value capture quote-aware — `(?:"[^"]*"|'[^']*'|[^\s,)]+)` after the `[=:]`, and in `_redact_kv` replace the whole (possibly-quoted) value with `[REDACTED]`. Add unit cases for `{"api_key":"x"}`, `{'password':'y'}`, `"authorization":"Bearer z"`. Same fix subsumes LOW S2 (comma-truncation).

- [ ] **H2 — `get_entity_edge` returns a bare `FactResult` with no `status` field, breaking the uniform success/error discriminator** `[needs-your-decision]`
  - File: `src/graphiti_mcp/tools/graph.py:72-83`; `src/graphiti_mcp/models.py:46-57`
  - Decision Type: needs-your-decision (PRODUCT-DECISION)
  - Convergence: conventions (HIGH), bugs (LOW), code-quality (related) — 3 dims.
  - Evidence: `FactResult.model_fields` has no `status` (verified). Every other tool returns a model with `status` (`FactSearchResponse`/`EpisodeListResponse`/`NodeSearchResponse`/`SuccessResponse`/`ErrorResponse` all carry it). So a client doing `result["status"] == "error"` works for 13 tools and KeyErrors on `get_entity_edge`'s success path.
  - Why it matters: the "no silent drop" contract (models.py:4-6) is described in terms of the `status` discriminator; this one tool silently violates it.
  - Options: (A) wrap in `FactResponse{status="success"; fact: FactResult}` mirroring the search responses (most consistent); (B) add `status="success"` default to `FactResult` (smaller, but double-encodes status when nested in `FactSearchResponse.facts[]`).

### MEDIUM

- [ ] **M1 — Spec risk-5 mitigation "validate dim at startup" not implemented** `[needs-your-decision]`
  - File: `src/graphiti_mcp/engine.py:46-80` (SPEC-COMPLIANCE)
  - Evidence: spec §5 lists four mitigations; three present (log resolved embedder, document, read-back *test*), but no startup probe asserts the embedder's real output dim == `EMBEDDER_DIM`. Grep confirms no validation site — only the config field, the log line, and passthrough to `OpenAIEmbedderConfig`. §11 Done-clause 3 ("misconfigured embedder → synchronous error") is therefore only partially delivered: missing-key misconfig raises `ProviderConfigError`, but a wrong dim/model silently yields empty search.
  - Options: (A) startup probe `await embedder.create([...])` + assert len == dim (adds one boot round-trip, needs embedder reachable at boot); (B) lazy validation on first `add_memory` (matches offline-Ollama assumption, surfaces as synchronous `ErrorResponse`); (C) accept + amend spec to drop the startup-validation wording.

- [ ] **M2 — `add_memory` MCP wrapper docstring/signature drops the `source` enum, so the tool schema the model sees omits `message|text|json`** `[FIX-NOW]`
  - File: `src/graphiti_mcp/server.py:62-75`
  - Evidence: wrapper types `source: str` with a prose docstring that omits valid values; the constraint lives only in the inner `tools/episodes.py:62-66` which the MCP client never sees. The model discovers the constraint only by triggering a runtime `ErrorResponse`.
  - Suggested fix: type `source: Literal["message","text","json"]` (enforces in schema) and surface the `reference_time` ISO-8601 hint in the wrapper docstring.

- [ ] **M3 — `get_status` reports `workspace` as the resolved group_id even when no workspace was configured** `[needs-your-decision]`
  - File: `src/graphiti_mcp/tools/admin.py:92-93`; `src/graphiti_mcp/config.py:90-93`
  - Evidence: both `workspace=` and `group_id=` are fed `s.default_group_id` (= `workspace or graphiti_group_id`). With only `GRAPHITI_GROUP_ID=main` set, status reports `workspace: "main"` though no workspace was ever set — misleading for a diagnostics tool.
  - Options: (A) report raw sources (`workspace=s.workspace or ""`, `group_id=s.graphiti_group_id`); (B) drop `workspace` from `StatusResponse`, report only effective `group_id`.

- [ ] **M4 — README config table omits `NEO4J_DATABASE` (read by code, shipped in `.env.example`)** `[FIX-NOW]`
  - File: `README.md:72-84` vs `.env.example:9` / `config.py:56`. Verified: 0 occurrences in README.
  - Suggested fix: add a `| NEO4J_DATABASE | neo4j | Target database |` row.

- [ ] **M5 — `LLM_SMALL_MODEL` is read by config + every provider but documented nowhere** `[FIX-NOW]`
  - File: `config.py:64-65`, `providers.py:45,61,81` vs README + `.env.example` (0 occurrences in either). Only undocumented settable field, breaking the repo's own "every var in .env.example" convention.
  - Suggested fix: add a commented `# LLM_SMALL_MODEL=` to `.env.example` + a README row; or drop it if intentionally internal.

- [ ] **M6 — Architecture diagram says "the 13 MCP tools" but 14 are registered** `[FIX-NOW]`
  - File: `README.md:244` vs 14 `@mcp.tool()` in `server.py` (verified count=14; Tools table + compare-matrix already say 14). Diagram is the stale outlier.
  - Suggested fix: change to "14 MCP tools".

- [ ] **M7 — `list_group_ids` does two unindexed full-graph scans (all nodes + all relationships)** `[needs-your-decision]`
  - File: `src/graphiti_mcp/tools/groups.py:19-25`
  - Evidence: `MATCH (n)` = AllNodesScan, `MATCH ()-[r]-()` = all-rel scan (traverses each edge twice). O(nodes + 2·edges), unbounded by group_id/limit — the only such query in the codebase. Bounded impact for this low-throughput tool, but a multi-second scan on a large graph.
  - Options: (A) accept (infrequent admin call) + document; (B) label-restrict `MATCH (n:Entity|Episodic|Community)`; (C) range index on `group_id` and drop the relationship arm if the edge-implies-node-group invariant holds (verify against graphiti-core first).

- [ ] **M8 — `_engine` is assigned and `initialize()` awaited OUTSIDE the lifespan `try/finally`; a startup failure leaks the Neo4j driver + leaves a non-None global** `[needs-your-decision]`
  - File: `src/graphiti_mcp/server.py:37-45`
  - Evidence: `_engine = GraphitiEngine(settings)` then `await _engine.initialize()` both precede `try:`. If `initialize()` raises (bad creds / index build), `finally` never runs → driver opened in `initialize()` is not closed and `_engine` stays set. (FastMCP aborts startup so no tool runs, but the cleanup relies on host behavior, not code.)
  - Options: (A) move `initialize()` inside `try/finally` (shutdown already null-guards a partial engine); (B) local try around init that calls shutdown + resets before re-raising; (C) accept + document lifespan-startup failure as terminal.

- [ ] **M9 — `add_triplet` group_id propagation onto nodes/edge is untested** `[testable]`
  - File: `src/graphiti_mcp/tools/episodes.py:113-125`; only success test asserts `assert_awaited_once()`, never inspects that nodes/edge carry the resolved gid (vs `add_memory` which has the equivalent). A namespace regression would pass the suite.

- [ ] **M10 — `add_memory` does not verify `reference_time`/`uuid` are forwarded to the engine** `[testable]`
  - File: `src/graphiti_mcp/tools/episodes.py:71-87`; rejection of bad `reference_time` is tested, but valid-parse-and-forward and the idempotency `uuid` are not — a dropped `uuid=uuid` (breaking idempotent re-ingest) would not fail any test.

- [ ] **M11 — `summarize_saga` empty-summary fallback branch uncovered** `[testable]`
  - File: `src/graphiti_mcp/tools/admin.py:49`; `or "(no summary produced)"` never exercised (only `Mock(summary="...")`).

- [ ] **M12 — No test for tool-use-before-init (`EngineNotInitializedError`)** `[testable]`
  - File: `engine.py:34-39`, `server.py:28-31`; the not-initialized safety net is entirely unverified (every fixture pre-sets `_graphiti`).

- [ ] **M13 — module-level `_engine` singleton blocks in-process wrapper testability** `[needs-your-decision]`
  - File: `server.py:25-31`; acceptable for stdio one-process-per-registration v1 (async-safe, atomic assignment) but forecloses cheap in-process integration tests of the wrapper layer and per-request workspace multiplexing if HTTP is ever added.
  - Options: (A) add a `set_engine()` test seam; (B) store engine on FastMCP request/lifespan context; (C) accept + document.

## Deferred / LOW (surfaced for awareness — not blocking)

- **errors.py** S2: key=value redaction truncates a comma-bearing value at the first `,` (subsumed by H1's quote-aware fix). `[FIX-NOW]`
- **graph.py:77-81** Q3: `get_entity_edge` labels every failure "not found", masking transient DB errors; sibling tools use neutral "Failed to..." `[FIX-NOW]`
- **providers.py:58,140** Q5: `"not-needed"` placeholder api_key is a repeated magic string → extract a named constant. `[FIX-NOW]`
- **admin.py:65-67** clear_graph rebuilds all indices on every clear though group-scoped `clear_data` leaves schema intact (verified) — redundant round-trip; convergence architecture+optimizations. `[decision]`
- **tools/*.py** `_resolve_group_id`/`_resolve_group_ids` duplicated 4× (2 name/arity variants) — hoist to engine or `tools/_common.py`; convergence conventions+code-quality. `[decision]`
- **episodes.py:68-76** naive `reference_time` accepted while the default is tz-aware UTC — normalize parsed input to aware UTC. `[decision]`
- **episodes.py:113-128** R1: `add_triplet` constructs nodes/edge OUTSIDE its try/except — a pydantic/construction error escapes raw instead of returning `ErrorResponse` like `add_memory`. `[testable]`
- **admin.py:44 / graph.py:64** R2: `summarize_saga`/`get_episode_entities` lack the `getattr` upstream-drift guard that `delete_episode` has (asymmetric resilience under the `<0.30` pin). `[intent-check]`
- **engine.py:41-44** A6: `driver` property untyped (`# noqa: ANN201`) — annotate return + caveat the backend coupling. `[fix-now]`
- **admin.py:1-2** C6: module docstring style outlier (no period, no body) vs siblings. `[fix-now]`
- **__init__.py** C7: only package module missing `from __future__ import annotations`. `[fix-now]`
- **groups.py / graph.py** A3: tools reach `engine.driver` + graphiti classmethods directly — the codebase's entire backend-coupling surface (3 call sites), deliberate for Neo4j-only v1. `[decision]`
- **server.py:214-222** A4: HTTP-transport seam mostly clean; the `_engine` global is the one painted-corner if HTTP multiplexes workspaces per-request. `[intent-check]`
- **engine.py:89-96** T5: `check_neo4j` only tested transitively via `get_status`. `[testable]`
- **episodes.py:92-95** T6: `add_memory` no-episode message branch untested. `[testable]`
- **config.py:82-85** T7: `workspace` lowercase alias + both-env-set precedence not directly env-tested. `[testable]`
- **Spec intent-checks** SC3 (14 tools vs ~13 — `list_group_ids` benign superset), SC4 (Done clauses 2 & 3 runtime/manual-only — don't mark "done" from green CI alone), SC5 (`GRAPHITI_WORKSPACE` rename vs spec's `GRAPHITI_GROUP_ID` — confirm public name & update §2/§3/§6). `[intent-check]`

## Verified clean (high-confidence)

- **No hallucinated API**: every `graphiti-core` method/signature/return-shape used by the tools verified against the installed package (incl. `summarize_saga`→`SagaNode`, `EagerResult` 3-tuple unpacking in `list_group_ids`, `clear_data`, edge classmethods).
- **All 4 spec `forbidden_actions` honored**: synchronous awaited writes (no queue anywhere), `OpenAIGenericClient` for base_url (#1116), no committed keys/.env (placeholders only), embedding-model default with matching dim.
- **`clear_graph` group-scope guard sound**: traced installed `clear_data` — the full-wipe branch (`group_ids=None`) is unreachable because the tool always passes `[gid]` with `gid` never None.
- **Anti-silent-drop guarantee genuinely proven**: `test_add_memory_propagates_failure_as_error_not_success` cannot pass trivially.
- **Injection-clean** (only static Cypher, all user input parameterized); **no catastrophic backtracking** in redaction; **`Mock(name=...)` gotcha correctly avoided** with `SimpleNamespace`; **fixtures isolate the dev `.env`** (`_env_file=None`); **#1116 guard tested** with the meaningful negative assertion.

## Caveats

- `pytest` is not installed in this review's base env (installs via `uv sync`); unit tests were green (66 passed, 2 skipped) in the prior run and were assessed statically here. Lint (`ruff`) and secret scan ran clean.

# Geniro Graphiti MCP

A clean-room [Model Context Protocol](https://modelcontextprotocol.io) server that
gives the Claude CLI a [Graphiti](https://github.com/getzep/graphiti)
knowledge-graph memory, backed by Neo4j.

It embeds `graphiti-core` **in-process** and writes **synchronously**: `add_memory`
awaits the actual graph write and returns the real result. There is no background
queue, so an ingestion failure is reported to you immediately instead of being
silently dropped while the tool reports success — the bug that affects the
upstream server and its forks.

## Why this exists

The upstream Graphiti MCP server enqueues each episode on an in-memory
`asyncio.Queue` and returns success right away. If processing fails, the error is
only logged; if the process restarts, the whole queue is lost. You get "success"
and an empty graph. This rewrite removes the queue entirely:

- **Synchronous awaited writes** — errors propagate to the caller.
- **Two-model config done right** — a main LLM *and* an embedder are both required
  and validated; a misconfigured embedder fails loudly instead of silently
  returning no search results.
- **A real test suite** — unit tests prove the no-silent-drop guarantee;
  testcontainers integration tests run against a real Neo4j.

## Requirements

- Python 3.11+
- A running Neo4j 5.26+ (use the bundled `docker-compose.yml`)
- An LLM provider key (OpenAI by default) **and** a reachable embedder
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`/`pipx`
- Docker (only for the integration tests / bundled Neo4j)

## Quick start

```bash
# 1. Start Neo4j
docker compose up -d

# 2. Configure
cp .env.example .env
# edit .env: set OPENAI_API_KEY, and point the embedder at a real embedding model

# 3. Install
uv sync                      # or: pip install .

# 4. Run (stdio)
uv run graphiti-mcp          # or just: graphiti-mcp
```

### Register with the Claude CLI

**Recommended — auto-updating install from PyPI.** Once the package is published
(see [Releasing & auto-update](#releasing--auto-update)), register it via `uvx` so
every Claude session launches the latest published version:

```bash
claude mcp add graphiti -- uvx --refresh geniro-graphiti-mcp@latest
```

`uvx … @latest` resolves the newest release on each start; `--refresh` bypasses
uv's cache so a version published moments ago is picked up immediately. Drop
`--refresh` if you prefer a faster startup and are happy for updates to land within
uv's normal cache window instead of on the very next launch.

Configuration comes from environment variables (there is no repo-local `.env`
alongside a `uvx` install). Pass them inline — this is also how you scope a
[workspace](#workspaces--memory-per-project) per project:

```bash
claude mcp add graphiti -- env \
  NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=demodemo \
  OPENAI_API_KEY=sk-… GRAPHITI_WORKSPACE=my-project \
  uvx --refresh geniro-graphiti-mcp@latest
```

For the Anthropic or Voyage extras, install from the extra-qualified spec:

```bash
claude mcp add graphiti -- uvx --refresh \
  --from 'geniro-graphiti-mcp[anthropic]@latest' geniro-graphiti-mcp
```

**Local development checkout.** When hacking on the server itself, point Claude at
your working tree so it runs your uncommitted code instead of a published release:

```bash
claude mcp add graphiti -- uv run --directory /path/to/geniro-graphiti-mcp graphiti-mcp
```

Then, from Claude: call `add_memory`, then `search_memory_facts`, and confirm the
fact comes back; `get_status` reports Neo4j connectivity and the resolved providers.

## Configuration

All configuration is via environment variables (or `.env`). See
[`.env.example`](.env.example) for the full list. Highlights:

| Variable | Default | Notes |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt endpoint |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `demodemo` | Match `docker-compose.yml` |
| `NEO4J_DATABASE` | `neo4j` | Target database |
| `LLM_PROVIDER` | `openai` | `openai` \| `anthropic` \| `openai_generic` |
| `LLM_MODEL` | `gpt-5.5` | Extraction model |
| `LLM_SMALL_MODEL` | — | Optional cheaper model for graphiti's low-stakes calls |
| `LLM_BASE_URL` | — | Required for `openai_generic` (LiteLLM/Ollama/vLLM) |
| `EMBEDDER_PROVIDER` | `ollama` | `openai` \| `ollama` \| `voyage` \| `openai_generic` |
| `EMBEDDER_MODEL` | `qwen3-embedding:8b` | **Must be an embedding model** |
| `EMBEDDER_DIM` | `4096` | **Must match the model's output dimension** |
| `EMBEDDER_BASE_URL` | `http://localhost:11434/v1` | Ollama default |
| `GRAPHITI_WORKSPACE` | `main` | Memory namespace — see [Workspaces](#workspaces--memory-per-project) |
| `GRAPHITI_GROUP_ID` | `main` | Backward-compatible alias for `GRAPHITI_WORKSPACE` |

### Workspaces — memory per project

A **workspace** partitions memory so a single server can serve many projects
without mixing their knowledge. It's a namespace key (`group_id` under the hood),
not a security boundary.

**Recommended: one registration per project.** Register the MCP separately for
each project with its own workspace via env — Claude in that project then only
ever reads and writes its own memory, with no chance of cross-contamination:

```bash
# In project A's repo:
claude mcp add graphiti -- env GRAPHITI_WORKSPACE=project-a \
  uvx --refresh geniro-graphiti-mcp@latest

# In project B's repo:
claude mcp add graphiti -- env GRAPHITI_WORKSPACE=project-b \
  uvx --refresh geniro-graphiti-mcp@latest
```

Everything (ingest, search, communities, `clear_graph`) is then scoped to that
workspace automatically — the agent never has to pass a key.

**Per-call override.** Even within one registration you can target another
workspace ad hoc: the ingest/search/admin tools accept an optional `group_id`
argument that overrides the configured default for that call. `get_status`
reports the active workspace, and `list_group_ids` lists every workspace present
in the graph.

### Provider notes

- **Two models are always needed.** An LLM extracts entities/relationships; an
  embedder vectorizes them for search. Configuring only an LLM yields empty
  search results.
- **OpenAI-compatible endpoints** (LiteLLM, Ollama, vLLM, OpenRouter) must use
  `LLM_PROVIDER=openai_generic`. This uses graphiti-core's `OpenAIGenericClient`
  so `LLM_BASE_URL` is honoured — the native `OpenAIClient` ignores `base_url`
  (graphiti issue #1116) and would silently hit api.openai.com.
- **Anthropic / Voyage** need optional extras: `uv pip install '.[anthropic]'`
  or `'.[voyage]'`.
- **No OpenAI key needed for non-OpenAI providers.** graphiti's default reranker
  is OpenAI-based; this server only uses it for `LLM_PROVIDER=openai`. Anthropic
  and OpenAI-compatible gateways fall back to the hybrid-search (RRF) ordering, so
  a pure-Anthropic or local setup never requires an unrelated `OPENAI_API_KEY`.
- **Embedding model, not chat model.** `qwen3-embedding:8b` is an embedding model;
  `qwen3:8b` is a chat model and will break search. `EMBEDDER_DIM` must match.

## Tools

| Tool | Purpose |
|---|---|
| `add_memory` | Ingest an episode (synchronous, awaited). |
| `add_memory_bulk` | Ingest many episodes in one batched, awaited call (faster than N× `add_memory`). |
| `add_triplet` | Add an explicit (source)-[edge]->(target) fact. |
| `search_memory_facts` | Search relationships (facts). |
| `search_nodes` | Search entity nodes. |
| `get_episodes` | List recent episodes. |
| `get_episode_entities` | Entities extracted from an episode. |
| `get_entity_edge` | Fetch one edge by UUID. |
| `delete_entity_edge` | Delete an edge by UUID. |
| `delete_episode` | Delete an episode by UUID. |
| `list_group_ids` | List the memory namespaces (group_ids) present in the graph. |
| `build_communities` | (Re)build community clusters. |
| `summarize_saga` | Summarize a thread of episodes. |
| `clear_graph` | Delete all data for one group (destructive, group-scoped). |
| `get_status` | Neo4j connectivity + resolved providers. |

## Testing

```bash
# Unit tests (mocked graphiti-core — no Neo4j needed)
uv run pytest tests/unit -q

# Integration tests (spins a real Neo4j via testcontainers; needs Docker + an
# embedder/LLM the container can reach)
uv run pytest -m integration -q

# Everything
uv run pytest -q
```

The unit suite includes the core guarantee: when a write fails, `add_memory`
returns an **error** synchronously — never a false success.

## How this compares

There are two other Graphiti MCP servers worth comparing against: the **upstream**
`getzep/graphiti` `mcp_server`, and the popular community fork
[`michabbb/graphiti-mcp-but-working`](https://github.com/michabbb/graphiti-mcp-but-working)
(an "enhanced fork" aimed at secure *public, multi-tenant* deployment). This
server targets a different use case — a **local, single-user** memory for the
Claude CLI — so the trade-offs differ deliberately.

### Tool surface

| Tool | This server | Upstream | michabbb fork |
|---|:---:|:---:|:---:|
| `add_memory` | ✅ (awaited) | ✅ (queued) | ✅ (queued) |
| `search_nodes` | ✅ | ✅ | ✅ (as `search_memory_nodes`) |
| `search_memory_facts` | ✅ | ✅ | ✅ |
| `get_episodes` / `delete_episode` | ✅ | ✅ | ✅ |
| `get_entity_edge` / `delete_entity_edge` | ✅ | ✅ | ✅ |
| `clear_graph` | ✅ (group-scoped) | ✅ | ✅ (password-gated) |
| `add_triplet` | ✅ | ✅ | ❌ |
| `get_episode_entities` | ✅ | ✅ | ❌ |
| `build_communities` | ✅ | ✅ | ❌ |
| `summarize_saga` | ✅ | ✅ | ❌ |
| `get_status` | ✅ (connectivity + providers) | ✅ | ❌ (status resource) |
| `list_group_ids` | ✅ | ❌ | ✅ |
| `add_memory_bulk` | ✅ (awaited batch) | ❌ | ❌ |
| `delete_everything_by_group_id` | ➖ (use `clear_graph`) | ❌ | ✅ |
| `get_queue_status` | ➖ N/A — no queue | ❌ | ✅ |

We carry the **full upstream tool surface** (using upstream's canonical names) and
add `list_group_ids` plus `add_memory_bulk` (an awaited batch ingest). The fork
dropped five upstream tools and added three of its own; two of those three
(`delete_everything_by_group_id`, `get_queue_status`) are either already covered
here (`clear_graph` is group-scoped) or meaningless without a queue.

### Capabilities this server has that the fork does not

- **Synchronous, awaited writes — no silent drops.** `add_memory` reports the real
  result. The fork keeps a queue (Redis-backed), and its worker still drops on a
  processing error (`fail(requeue=False)`, no dead-letter) — the same bug class
  this rewrite was built to eliminate.
- **A real test suite.** Upstream and the fork ship **zero** tests; this server has
  60+ unit tests (including the no-silent-drop guarantee) plus a testcontainers
  integration round-trip.
- **Multiple LLM providers** — OpenAI, Anthropic, and any OpenAI-compatible endpoint
  (LiteLLM / Ollama / vLLM). The fork is OpenAI-only (Azure was removed).
- **Multiple embedders** — OpenAI / Ollama / Voyage, with a validated local default.
- **The `base_url` fix (#1116)** — `OpenAIGenericClient` for compatible endpoints, so
  Ollama/LiteLLM actually work. (The fork is OpenAI-direct, so it sidesteps rather
  than fixes this.)
- **Secret redaction** in error messages returned to the client.
- **Newer graphiti-core (0.29.2)**, which handles gpt-5/o1/o3 reasoning models
  natively — so the fork's manual `reasoning=None` workaround is unnecessary here.

### Fork features intentionally **not** included (and why)

These exist in the fork to support **public, multi-tenant hosting**. They are out of
scope for a local single-user stdio server — including them would add the exact
queue/ops/auth surface this rewrite set out to remove:

| Fork feature | Why it's omitted here |
|---|---|
| Redis-backed persistent queue (BRPOPLPUSH) | We don't queue at all — writes are awaited, which is what makes failures visible. |
| Token / nonce authentication middleware | A local stdio server has no network surface to authenticate. |
| Streamable HTTP / SSE transport | stdio only for v1 (an env-driven transport switch could be added later). |
| `X-Group-Id` multi-tenant context + allowlist | Single-user; `group_id` is a plain namespace, not a security boundary. |
| DNS-rebinding protection (`ALLOWED_HOSTS`) | Only relevant when bound to a network interface. |
| Password-gated `clear_graph` | `clear_graph` is group-scoped and explicit; a shared password adds little locally. |

Borrowed from the fork where it made sense regardless of scope: **`list_group_ids`**,
**telemetry disabled by default**, and a **tracked `uv.lock`** for reproducible installs.

## Architecture

```
Claude CLI ──stdio──> graphiti-mcp (FastMCP)
                          │
                          ├─ config.py     env/.env settings
                          ├─ providers.py  LLM + embedder factories
                          ├─ engine.py     Graphiti(Neo4jDriver, llm, embedder)
                          ├─ tools/        the 15 MCP tools (await writes)
                          └─ models.py     pydantic responses
                                 │
                                 └─ graphiti-core ──Bolt──> Neo4j
```

The engine is embedded directly (architecture A) — no separate Graphiti REST
service, no network hop, no async-202 durability bug.

## Releasing & auto-update

New versions reach every `uvx … @latest` registration automatically. The pipeline:

1. **Bump the version** in `pyproject.toml` (`version = "X.Y.Z"`).
2. **Merge to `main`.** On every push to `main`, [`.github/workflows/release.yml`](.github/workflows/release.yml)
   reads that version and checks PyPI. If the exact version is not published yet, it
   runs the unit tests, builds the wheel + sdist, and publishes to PyPI via **trusted
   publishing** (OIDC — no API token is stored in the repo). If the version is
   unchanged (already on PyPI), the job is a no-op, so unrelated pushes never publish.
3. **Clients update on next launch.** Because registrations use
   `geniro-graphiti-mcp@latest`, the next time Claude starts the server it resolves
   and runs the new release (immediately with `--refresh`, otherwise within uv's
   cache window).

### One-time PyPI setup (required before the first publish)

Trusted publishing must be authorized once on PyPI, or the publish step fails:

1. Sign in at <https://pypi.org> → **Your projects → Publishing**, or
   **Account → Publishing → Add a pending publisher** if the project does not exist
   on PyPI yet.
2. Register a **GitHub** trusted publisher with:
   - **PyPI project name:** `geniro-graphiti-mcp`
   - **Owner:** `geniro-io`
   - **Repository:** `geniro-graphiti-mcp`
   - **Workflow filename:** `release.yml`
   - **Environment:** *(leave blank)*
3. Merge a version bump to `main` (the initial `0.1.0` counts) and watch the
   **Release** workflow publish it.

No PyPI token is ever stored — GitHub's OIDC identity authorizes each publish.

## License

Apache-2.0.

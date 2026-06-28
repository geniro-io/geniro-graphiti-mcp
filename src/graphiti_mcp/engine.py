"""Graphiti engine lifecycle.

``GraphitiEngine`` owns the in-process :class:`graphiti_core.Graphiti` instance:
it builds the Neo4j driver + LLM + embedder, creates indices/constraints on
startup, and closes the driver on shutdown. Tools receive the engine and call
through ``engine.client`` / ``engine.driver``.
"""

from __future__ import annotations

import logging

from graphiti_core import Graphiti
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.driver.neo4j_driver import Neo4jDriver

from .config import Settings
from .providers import (
    ProviderConfigError,
    build_cross_encoder,
    build_embedder,
    build_llm_client,
)

logger = logging.getLogger(__name__)


class EngineNotInitializedError(RuntimeError):
    """Raised when a tool is used before :meth:`GraphitiEngine.initialize`."""


class GraphitiEngine:
    """Owns the Graphiti instance and its lifecycle."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._graphiti: Graphiti | None = None
        # Set once the embedder's real output dimension has been verified against
        # EMBEDDER_DIM (lazy, on first ingest) — see :meth:`ensure_embedder_dim`.
        self._embedder_checked = False

    @property
    def client(self) -> Graphiti:
        if self._graphiti is None:
            raise EngineNotInitializedError(
                "GraphitiEngine.initialize() must be awaited before use."
            )
        return self._graphiti

    @property
    def driver(self) -> GraphDriver:
        """The underlying graph driver (for direct node/edge lookups).

        Couples the caller to the concrete backend's return contract (e.g.
        Neo4j's ``EagerResult`` tuple), so use it only where graphiti's client
        API has no equivalent (raw Cypher in ``groups``, edge classmethods).
        """
        return self.client.driver

    async def initialize(self) -> None:
        """Build the Graphiti instance and create indices/constraints.

        Constructing the driver and clients is cheap; the first real Neo4j round
        trip happens in :meth:`build_indices_and_constraints`, so a bad
        connection surfaces here at startup rather than mid-request.
        """
        s = self.settings
        driver = Neo4jDriver(
            uri=s.neo4j_uri,
            user=s.neo4j_user,
            password=s.neo4j_password,
            database=s.neo4j_database,
        )
        llm_client = build_llm_client(s)
        embedder = build_embedder(s)
        # Pass an explicit reranker so construction never requires an unrelated
        # OpenAI key (graphiti defaults to an OpenAI cross-encoder otherwise).
        cross_encoder = build_cross_encoder(s)

        self._graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
            max_coroutines=s.semaphore_limit,
        )

        logger.info(
            "Graphiti initialized: neo4j=%s llm=%s/%s embedder=%s/%s(dim=%d) workspace=%s",
            s.neo4j_uri,
            s.llm_provider.value,
            s.llm_model,
            s.embedder_provider.value,
            s.embedder_model,
            s.embedder_dim,
            s.default_group_id,
        )
        await self._graphiti.build_indices_and_constraints()

    async def shutdown(self) -> None:
        """Close the driver and release the Graphiti instance."""
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None
            logger.info("Graphiti shut down.")

    async def ensure_embedder_dim(self) -> None:
        """Verify the embedder's output dimension matches ``EMBEDDER_DIM`` (once).

        A wrong ``EMBEDDER_DIM`` (or a non-embedding model) otherwise degrades
        search silently — the spec's risk-5 failure mode. We probe lazily on the
        first ingest rather than at startup so boot does not require the embedder
        to be reachable (the default Ollama embedder may not be up yet); the
        mismatch then surfaces as a synchronous error on the first write instead
        of as empty search results later.

        Raises:
            ProviderConfigError: if the probe vector's length differs from the
                configured ``EMBEDDER_DIM``.
        """
        if self._embedder_checked:
            return
        vector = await self.client.embedder.create("dimension probe")
        actual = len(vector)
        if actual != self.settings.embedder_dim:
            raise ProviderConfigError(
                f"Embedder '{self.settings.embedder_model}' produced "
                f"{actual} dimensions but EMBEDDER_DIM={self.settings.embedder_dim}. "
                f"Set EMBEDDER_DIM={actual} or configure the correct embedding model."
            )
        self._embedder_checked = True

    async def check_neo4j(self) -> bool:
        """Return True if a trivial Cypher query round-trips."""
        try:
            await self.driver.execute_query("RETURN 1 AS ok")
            return True
        except Exception:  # noqa: BLE001 - health check must not raise
            logger.exception("Neo4j health check failed")
            return False

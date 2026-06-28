"""Unit-test environment isolation.

Several unit tests assert Settings DEFAULTS via ``Settings(_env_file=None)``.
The catch: importing ``graphiti_mcp.engine`` (transitively ``graphiti_core`` /
its LLM-client deps) calls ``load_dotenv()`` at import time, which loads the
repo's ``.env`` into ``os.environ``. ``tests/conftest.py`` imports
``GraphitiEngine``, so during a pytest run the real server config
(``LLM_PROVIDER=anthropic``, ``GRAPHITI_WORKSPACE=main``, ``NEO4J_PASSWORD=...`` …)
sits in ``os.environ`` for the whole session. ``_env_file=None`` disables
pydantic-settings' OWN dotenv read but does NOT undo vars already in
``os.environ`` — so the default-asserting tests see the live ``.env`` and fail
(they pass only in a clean checkout with no ``.env``, e.g. CI). That
env-sensitivity is itself a bug, not a steady state.

This autouse fixture strips every env var that ``Settings`` reads — derived from
the model (field names + ``AliasChoices``) so it never drifts as fields are
added — making the unit suite hermetic regardless of any loaded ``.env``. Scoped
to ``tests/unit/`` so the integration suite keeps its real credentials.

Tests that exercise env reading set their own vars via ``monkeypatch.setenv`` in
the test body, which runs AFTER this fixture, so they are unaffected.
"""

from __future__ import annotations

import pytest
from pydantic import AliasChoices

from graphiti_mcp.config import Settings


def _settings_env_var_names() -> set[str]:
    """Every env var name (any case) that ``Settings`` would read."""
    names: set[str] = set()
    for field_name, field in Settings.model_fields.items():
        names.add(field_name)
        alias = field.validation_alias
        if isinstance(alias, str):
            names.add(alias)
        elif isinstance(alias, AliasChoices):
            names.update(choice for choice in alias.choices if isinstance(choice, str))
    # case_sensitive=False → an env var matches in any case; clear both forms.
    return {n.upper() for n in names} | {n.lower() for n in names}


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _settings_env_var_names():
        monkeypatch.delenv(name, raising=False)

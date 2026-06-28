"""Secret redaction in client-facing error messages."""

from __future__ import annotations

import pytest

from graphiti_mcp.errors import redact_secrets, safe_error


@pytest.mark.parametrize(
    "raw",
    [
        "auth failed: sk-abcDEF1234567890",
        "Authorization: Bearer abc.def.ghi token rejected",
        "api_key=sk-live-9999 was invalid",
        "api-key: supersecretvalue",
        "password=hunter2 denied",
        "bolt://neo4j:mypassword@localhost:7687 unreachable",
    ],
)
def test_secrets_are_redacted(raw: str) -> None:
    cleaned = redact_secrets(raw)
    assert "[REDACTED]" in cleaned
    for leaked in ("sk-abcDEF1234567890", "sk-live-9999", "supersecretvalue", "hunter2", "mypassword"):
        assert leaked not in cleaned


@pytest.mark.parametrize(
    ("raw", "leaked"),
    [
        # The dominant JSON/dict error-body shape: quoted key AND quoted value.
        ('{"openai_api_key": "proxy-LEAKED1234567"}', "proxy-LEAKED1234567"),
        ("{'api_key': 'LEAKEDvalue'}", "LEAKEDvalue"),
        ('{"password": "db-LEAKED-pw"}', "db-LEAKED-pw"),
        ('"authorization": "Bearer LEAKEDtoken"', "LEAKEDtoken"),
        # A comma-bearing quoted secret must be redacted whole, not truncated.
        ('{"secret": "a,b,c,LEAKED"}', "a,b,c,LEAKED"),
    ],
)
def test_quoted_keyvalue_secrets_are_redacted(raw: str, leaked: str) -> None:
    cleaned = redact_secrets(raw)
    assert "[REDACTED]" in cleaned
    assert leaked not in cleaned


def test_non_secret_text_is_preserved() -> None:
    msg = "Neo4j connection refused at bolt://localhost:7687"
    # No credentials here, so the diagnostic text survives intact.
    assert redact_secrets(msg) == msg


def test_safe_error_stringifies_and_redacts() -> None:
    exc = RuntimeError("401: api_key=sk-zzz999 rejected")
    out = safe_error(exc)
    assert "sk-zzz999" not in out
    assert "[REDACTED]" in out
    # The non-secret context ("401") is retained for diagnosis.
    assert "401" in out

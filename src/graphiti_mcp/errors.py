"""Error-message sanitization.

Tool failures return the underlying exception text to the caller so problems are
diagnosable (Neo4j unreachable, bad model name, etc.). But upstream LLM/DB client
exceptions can embed credentials (an API key in an auth-failure body, a bearer
token, a connection string with a password). ``safe_error`` scrubs those patterns
from the client-facing string; the full, unredacted exception still goes to
stderr via ``logger.exception`` for the operator.
"""

from __future__ import annotations

import re

_REDACTED = "[REDACTED]"

# Order matters: more specific patterns first.
# OpenAI / Anthropic-style keys: sk-..., sk-ant-...
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{6,}")
# Bearer tokens in auth headers.
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")
# Sensitive ``field = value`` / ``field: value`` — INCLUDING the quoted JSON/dict
# shape (`"api_key": "secret"`) that dominates LLM/HTTP/DB client error bodies.
# The field name may be a suffix of a compound key (``openai_api_key``) and may be
# quote-wrapped; the value may be quoted (captured through commas, so a comma-
# bearing secret is fully scrubbed) or bare.
_KV_PATTERN = re.compile(
    r"(?i)"
    r"(['\"]?[\w.\-]*(?:api[_-]?key|authorization|access[_-]?token|password|secret|token)[\w.\-]*['\"]?)"
    r"(\s*[=:]\s*)"
    r"""(\"[^\"]*\"|'[^']*'|[^\s,)]+)"""
)
# Credentials embedded in a URL (scheme://user:pass@host).
_URL_CRED_PATTERN = re.compile(r"://[^\s:/@]+:[^\s:/@]+@")


def redact_secrets(text: str) -> str:
    """Replace secret-looking substrings in ``text`` with ``[REDACTED]``."""
    text = _SK_PATTERN.sub(_REDACTED, text)
    text = _BEARER_PATTERN.sub(_REDACTED, text)
    # Keep the field name + separator, redact the whole (possibly quoted) value.
    text = _KV_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", text)
    text = _URL_CRED_PATTERN.sub("://" + _REDACTED + "@", text)
    return text


def safe_error(exc: BaseException) -> str:
    """Return a client-safe string for ``exc`` with secrets redacted."""
    return redact_secrets(str(exc))

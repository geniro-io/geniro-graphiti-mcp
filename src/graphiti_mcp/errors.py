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

# Order matters: more specific patterns first.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # OpenAI / Anthropic-style keys: sk-..., sk-ant-...
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    # Bearer tokens in auth headers.
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    # key=value / key: value for sensitive field names.
    re.compile(
        r"(?i)\b(api[_-]?key|authorization|access[_-]?token|password|secret|token)\b"
        r"\s*[=:]\s*[\"']?[^\s\"',)]+"
    ),
    # Credentials embedded in a URL (scheme://user:pass@host).
    re.compile(r"://[^\s:/@]+:[^\s:/@]+@"),
)

_REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> str:
    """Replace secret-looking substrings in ``text`` with ``[REDACTED]``."""
    text = _SECRET_PATTERNS[0].sub(_REDACTED, text)
    text = _SECRET_PATTERNS[1].sub(_REDACTED, text)
    # For key=value, keep the field name, redact only the value.
    text = _SECRET_PATTERNS[2].sub(lambda m: _redact_kv(m.group(0)), text)
    text = _SECRET_PATTERNS[3].sub("://" + _REDACTED + "@", text)
    return text


def _redact_kv(match: str) -> str:
    # Split on the first = or : and redact the value side only.
    separator = "=" if "=" in match else ":"
    key, _, _value = match.partition(separator)
    return f"{key}{separator}{_REDACTED}"


def safe_error(exc: BaseException) -> str:
    """Return a client-safe string for ``exc`` with secrets redacted."""
    return redact_secrets(str(exc))

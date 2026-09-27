"""Secret redaction shared by logging and client error messages.

httpx logs request URLs at INFO via lazy %-args, so the key value lives in
record.args, not record.msg — the filter rewrites both. httpx exception text
also embeds the full URL, so clients must pass their error messages through
`redact_secrets` before raising (the logging filter never sees exceptions that
are stored in run state or returned in HTTP responses).

Covers FMP (`apikey=`), FRED (`api_key=`) and token-style query params.
"""
import logging
import re

_SECRET_PARAM_RE = re.compile(
    r"(?P<name>\b(?:api_?key|access_token|token))=[^&\s\"']+",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    """Replace the value of any secret-bearing query param with REDACTED."""
    return _SECRET_PARAM_RE.sub(r"\g<name>=REDACTED", text)


def _needs_redaction(text: str) -> bool:
    return _SECRET_PARAM_RE.search(text) is not None


class ApiKeyRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and _needs_redaction(record.msg):
            record.msg = redact_secrets(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_secrets(str(a)) if _needs_redaction(str(a)) else a
                for a in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                k: redact_secrets(str(v)) if _needs_redaction(str(v)) else v
                for k, v in record.args.items()
            }
        return True

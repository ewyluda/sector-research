"""Logging filters shared by the app. Currently: FMP apikey redaction.

httpx logs request URLs at INFO via lazy %-args, so the key value lives in
record.args, not record.msg — the filter rewrites both.
"""
import logging
import re

_APIKEY_RE = re.compile(r"apikey=[^&\s\"']+")


class ApiKeyRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "apikey=" in record.msg:
            record.msg = _APIKEY_RE.sub("apikey=REDACTED", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _APIKEY_RE.sub("apikey=REDACTED", str(a))
                if "apikey=" in str(a) else a
                for a in record.args
            )
        return True

"""rsyslog shipping via stdlib SysLogHandler.

LogSink is constructed once at app boot and stashed on `app`. It is a thin
wrapper around `logging.handlers.SysLogHandler` that swallows network errors
so a dead rsyslog server never breaks a refresh. When `RSYSLOG_HOST` is not
configured the sink is a no-op.
"""
from __future__ import annotations

import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

_VALID_PROTOS = {"tcp": socket.SOCK_STREAM, "udp": socket.SOCK_DGRAM}


class LogSink:
    def __init__(self, host, port, proto, facility, app_name="clash-converter"):
        # Defer the import so the module is loadable on systems where the
        # handler has been patched (some test fixtures mock it).
        from logging.handlers import SysLogHandler

        self.host = host
        self.app_name = app_name
        self._handler = None
        if not host:
            return
        sock_type = _VALID_PROTOS.get(proto)
        if sock_type is None:
            logger.warning("Unknown RSYSLOG_PROTO=%r, expected tcp|udp; disabling sink", proto)
            return
        try:
            self._handler = SysLogHandler(
                address=(host, int(port)),
                facility=facility,
                socktype=sock_type,
            )
        except (OSError, socket.error) as e:
            logger.warning("Could not configure SysLogHandler to %s:%s: %s", host, port, e)
            self._handler = None

    @property
    def enabled(self):
        return self._handler is not None

    def emit(self, event_type, **fields):
        if self._handler is None:
            return
        # Compact key=value payload. The rsyslog receiver can grep by
        # `event=...` and `provider=...`.
        pairs = " ".join(
            f"{k}={_quote(v)}" for k, v in fields.items() if v is not None
        )
        message = f"{event_type} {pairs}".strip()
        record = logging.LogRecord(
            name=self.app_name,
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        try:
            self._handler.emit(record)
        except (OSError, socket.error) as e:
            # Don't kill a refresh because the log server died. Log once.
            logger.warning("rsyslog emit to %s failed: %s", self.host, e)

    def close(self):
        if self._handler is not None:
            try:
                self._handler.close()
            except Exception:  # pragma: no cover - best-effort teardown
                pass
            self._handler = None


def _quote(value: Any) -> str:
    s = str(value)
    if any(ch in s for ch in " \t\""):
        return '"' + s.replace('"', '\\"') + '"'
    return s

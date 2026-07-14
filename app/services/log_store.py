"""Append-only JSONL event log.

LogStore is the local "accumulated logs" sink — every refresh stage transition
and every public subscription query writes one line to a JSONL file under
`DATA_DIR/logs/events.jsonl`. The file is pruned hourly by APScheduler to keep
only the last `LOG_RETENTION_DAYS` entries. The management UI exposes a Clear
button that calls `clear()` (truncate).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone


EVENT_FILENAME = "events.jsonl"


class LogStore:
    def __init__(self, logs_dir):
        self.logs_dir = logs_dir

    # ---- path ----------------------------------------------------------
    def _path(self):
        os.makedirs(self.logs_dir, exist_ok=True)
        return os.path.join(self.logs_dir, EVENT_FILENAME)

    # ---- writes --------------------------------------------------------
    def append(self, event):
        """Append one event as a single JSON line. Atomic per line.

        Reads the existing file into a temp path, appends the new line, and
        `os.replace`s the temp over the live file. Cost is O(file size) per
        append, which is acceptable because the log is small by design
        (capped at ~7 days, pruned hourly).
        """
        if "ts" not in event:
            event = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        else:
            event = dict(event)
        line = json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"
        path = self._path()
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                if os.path.exists(path):
                    with open(path, "rb") as src:
                        f.write(src.read())
                f.write(line.encode("utf-8"))
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
        return event

    # ---- reads ---------------------------------------------------------
    def entries(self, provider_id=None, limit=200):
        """Return newest-first list of events. Bounded by `limit`.

        The file is small by design; reading it whole is fine and keeps the
        implementation simple. Filter by `provider_id` if provided.
        """
        path = self._path()
        if not os.path.exists(path):
            return []
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if provider_id is not None and obj.get("provider_id") != provider_id:
                    continue
                out.append(obj)
        out.reverse()
        if limit is not None and limit > 0:
            out = out[:limit]
        return out

    # ---- retention -----------------------------------------------------
    def purge_older_than(self, days):
        """Rewrite the file keeping only lines whose `ts >= now - days`.

        Returns the number of lines removed. Atomic via temp-file + replace.
        """
        path = self._path()
        if not os.path.exists(path):
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept_lines = []
        removed = 0
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw_stripped = raw.rstrip("\n")
                if not raw_stripped:
                    continue
                try:
                    obj = json.loads(raw_stripped)
                except json.JSONDecodeError:
                    continue
                ts = _parse_iso(obj.get("ts"))
                if ts is not None and ts < cutoff:
                    removed += 1
                    continue
                kept_lines.append(raw if raw.endswith("\n") else raw + "\n")
        _atomic_write_text(path, "".join(kept_lines))
        return removed

    # ---- manual clear --------------------------------------------------
    def clear(self):
        """Truncate the file. Returns the number of lines removed."""
        path = self._path()
        count = 0
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                count = sum(1 for line in f if line.strip())
            open(path, "w").close()
        return count


# ---- helpers ---------------------------------------------------------------


def _atomic_write_text(path, text):
    """Write `text` to `path` atomically via temp-file + os.replace."""
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def _parse_iso(value):
    if not value:
        return None
    try:
        s = value[:-1] + "+00:00" if value.endswith("Z") else value
        dt = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

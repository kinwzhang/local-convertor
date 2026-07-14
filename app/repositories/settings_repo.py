"""Repository helpers for the AppSettings singleton."""
from app.extensions import db
from app.models.settings import AppSettings


def get_settings():
    """Return the AppSettings row, creating it with defaults if missing.

    The migration seeds the singleton row, but tests and fresh installs may
    transiently lack it; `get_settings` is idempotent.
    """
    s = db.session.query(AppSettings).first()
    if s is None:
        s = AppSettings(id=1)
        db.session.add(s)
        db.session.commit()
        db.session.refresh(s)
    return s


def update_settings(**fields):
    """Mutate the singleton row in place. Returns the updated row.

    Validates ports / proto / retention before commit. Unknown fields raise.
    """
    s = get_settings()

    if "rsyslog_host" in fields:
        host = (fields["rsyslog_host"] or "").strip() or None
        s.rsyslog_host = host

    if "rsyslog_port" in fields:
        port = int(fields["rsyslog_port"])
        if not (1 <= port <= 65535):
            raise ValueError(f"rsyslog_port must be 1..65535, got {port}")
        s.rsyslog_port = port

    if "rsyslog_proto" in fields:
        proto = (fields["rsyslog_proto"] or "").lower()
        if proto not in ("tcp", "udp"):
            raise ValueError(f"rsyslog_proto must be tcp|udp, got {fields['rsyslog_proto']!r}")
        s.rsyslog_proto = proto

    if "rsyslog_facility" in fields:
        facility = (fields["rsyslog_facility"] or "").strip()
        if not facility:
            raise ValueError("rsyslog_facility cannot be empty")
        s.rsyslog_facility = facility

    if "log_retention_days" in fields:
        days = int(fields["log_retention_days"])
        if days < 1:
            raise ValueError("log_retention_days must be >= 1")
        s.log_retention_days = days

    db.session.commit()
    db.session.refresh(s)
    return s

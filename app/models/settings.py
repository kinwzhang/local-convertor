"""Application-wide settings (log forwarding, retention).

The table is intentionally singleton-shaped: a single row with id=1 keeps
the read path trivial (`AppSettings.query.first()`). UI writes mutate that
row in place. Any new app-wide config (UI-managed) belongs here.
"""
from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class AppSettings(db.Model):
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True, default=1)
    rsyslog_host = db.Column(db.String(255), nullable=True)
    rsyslog_port = db.Column(db.Integer, nullable=False, default=514)
    rsyslog_proto = db.Column(db.String(8), nullable=False, default="tcp")
    rsyslog_facility = db.Column(db.String(32), nullable=False, default="local0")
    log_retention_days = db.Column(db.Integer, nullable=False, default=7)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.CheckConstraint("rsyslog_proto IN ('tcp', 'udp')", name="ck_settings_proto"),
        db.CheckConstraint("rsyslog_port BETWEEN 1 AND 65535", name="ck_settings_port"),
        db.CheckConstraint("log_retention_days >= 1", name="ck_settings_retention"),
    )

    def to_dict(self):
        return {
            "rsyslog_host": self.rsyslog_host,
            "rsyslog_port": self.rsyslog_port,
            "rsyslog_proto": self.rsyslog_proto,
            "rsyslog_facility": self.rsyslog_facility,
            "log_retention_days": self.log_retention_days,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

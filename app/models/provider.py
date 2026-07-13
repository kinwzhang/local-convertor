import secrets
from datetime import datetime, timezone

from app.extensions import db


def _generate_token():
    return secrets.token_hex(16)


def _iso_utc(dt):
    """Serialize a datetime as ISO-8601 with explicit +00:00.

    SQLite strips timezone info on round-trip, so naive datetimes read
    back from the DB must be treated as UTC.  Appending +00:00 prevents
    JavaScript from interpreting the timestamp as *local* browser time.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _utcnow():
    return datetime.now(timezone.utc)


class Provider(db.Model):
    __tablename__ = "providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    source_url = db.Column(db.Text, nullable=False)
    public_token = db.Column(db.String(32), unique=True, nullable=False, default=_generate_token)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    schedule_type = db.Column(db.String(20), nullable=False, default="disabled")
    schedule_day_of_month = db.Column(db.Integer, nullable=True)
    schedule_day_of_week = db.Column(db.Integer, nullable=True)
    schedule_time_of_day = db.Column(db.String(5), nullable=True)
    schedule_interval_hours = db.Column(db.Integer, nullable=True)

    last_check_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_success_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    current_version = db.Column(db.Integer, nullable=True)

    ua_mode = db.Column(db.String(32), nullable=False, default="auto")

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    versions = db.relationship("SubscriptionVersion", backref="provider", lazy="dynamic", cascade="all, delete-orphan")
    update_runs = db.relationship("UpdateRun", backref="provider", lazy="dynamic", cascade="all, delete-orphan")

    def rotate_token(self):
        self.public_token = _generate_token()
        self.updated_at = _utcnow()

    def to_dict(self, include_source_url=False):
        d = {
            "id": self.id,
            "name": self.name,
            "public_token": self.public_token,
            "enabled": self.enabled,
            "ua_mode": self.ua_mode,
            "schedule": {
                "type": self.schedule_type,
                "day_of_month": self.schedule_day_of_month,
                "day_of_week": self.schedule_day_of_week,
                "time_of_day": self.schedule_time_of_day,
                "interval_hours": self.schedule_interval_hours,
            },
            "last_check_at": _iso_utc(self.last_check_at),
            "last_success_at": _iso_utc(self.last_success_at),
            "last_error": self.last_error,
            "current_version": self.current_version,
            "created_at": _iso_utc(self.created_at),
            "updated_at": _iso_utc(self.updated_at),
        }
        if include_source_url:
            d["source_url"] = self.source_url
        return d


class SubscriptionVersion(db.Model):
    __tablename__ = "subscription_versions"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("providers.id"), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    raw_hash = db.Column(db.String(64), nullable=False)
    converted_hash = db.Column(db.String(64), nullable=False)
    raw_path = db.Column(db.Text, nullable=False)
    converted_path = db.Column(db.Text, nullable=False)
    node_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("provider_id", "sequence", name="uq_provider_sequence"),
    )


class UpdateRun(db.Model):
    __tablename__ = "update_runs"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("providers.id"), nullable=False)
    trigger = db.Column(db.String(20), nullable=False)
    stage = db.Column(db.String(20), nullable=False, default="querying")
    status = db.Column(db.String(20), nullable=False, default="running")
    message = db.Column(db.Text, nullable=True)
    error_details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "run_id": self.id,
            "provider_id": self.provider_id,
            "provider_name": self.provider.name if self.provider else "",
            "trigger": self.trigger,
            "stage": self.stage,
            "status": self.status,
            "message": self.message,
            "created_at": _iso_utc(self.created_at),
            "completed_at": _iso_utc(self.completed_at),
        }

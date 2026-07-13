from datetime import datetime, timezone

from app.extensions import db
from app.models.provider import Provider, SubscriptionVersion, UpdateRun


def list_providers():
    return Provider.query.order_by(Provider.created_at).all()


def get_provider(provider_id):
    return db.session.get(Provider, provider_id)


def get_provider_by_token(token):
    return Provider.query.filter_by(public_token=token).first()


def create_provider(name, source_url, schedule, ua_mode="auto"):
    p = Provider(
        name=name,
        source_url=source_url,
        schedule_type=schedule.get("type", "disabled"),
        schedule_day_of_month=schedule.get("day_of_month"),
        schedule_day_of_week=schedule.get("day_of_week"),
        schedule_time_of_day=schedule.get("time_of_day"),
        schedule_interval_hours=schedule.get("interval_hours"),
        ua_mode=ua_mode,
    )
    db.session.add(p)
    db.session.commit()
    return p


def update_provider(provider, data):
    if "name" in data:
        provider.name = data["name"]
    if "source_url" in data:
        provider.source_url = data["source_url"]
    if "enabled" in data:
        provider.enabled = data["enabled"]
    if "ua_mode" in data:
        provider.ua_mode = data["ua_mode"]
    if "schedule" in data:
        s = data["schedule"]
        provider.schedule_type = s.get("type", provider.schedule_type)
        provider.schedule_day_of_month = s.get("day_of_month")
        provider.schedule_day_of_week = s.get("day_of_week")
        provider.schedule_time_of_day = s.get("time_of_day")
        provider.schedule_interval_hours = s.get("interval_hours")
    provider.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return provider


def delete_provider(provider):
    db.session.delete(provider)
    db.session.commit()


def get_current_version(provider_id):
    return (
        SubscriptionVersion.query
        .filter_by(provider_id=provider_id)
        .order_by(SubscriptionVersion.sequence.desc())
        .first()
    )


def create_version(provider_id, sequence, raw_hash, converted_hash, raw_path, converted_path, node_count):
    v = SubscriptionVersion(
        provider_id=provider_id,
        sequence=sequence,
        raw_hash=raw_hash,
        converted_hash=converted_hash,
        raw_path=raw_path,
        converted_path=converted_path,
        node_count=node_count,
    )
    db.session.add(v)
    db.session.commit()
    return v


def get_versions(provider_id, limit=5):
    return (
        SubscriptionVersion.query
        .filter_by(provider_id=provider_id)
        .order_by(SubscriptionVersion.sequence.desc())
        .limit(limit)
        .all()
    )


def delete_version(version):
    db.session.delete(version)
    db.session.commit()


def create_update_run(provider_id, trigger):
    run = UpdateRun(provider_id=provider_id, trigger=trigger)
    db.session.add(run)
    db.session.commit()
    return run


def update_run_stage(run, stage, message=None):
    run.stage = stage
    run.message = message
    db.session.commit()
    return run


def complete_update_run(run, status, message=None, error_details=None):
    run.status = status
    run.stage = "finished" if status == "success" else "failed"
    run.message = message
    run.error_details = error_details
    run.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return run


def list_update_runs(provider_id=None, limit=50):
    q = UpdateRun.query
    if provider_id:
        q = q.filter_by(provider_id=provider_id)
    return q.order_by(UpdateRun.created_at.desc()).limit(limit).all()

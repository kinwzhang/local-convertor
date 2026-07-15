import json
import queue
import threading
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, Response, current_app

from app.extensions import db
from app.models.provider import Provider, UpdateRun
from app.repositories.provider_repo import (
    list_providers,
    get_provider,
    get_provider_by_token,
    create_provider,
    update_provider,
    delete_provider,
    list_update_runs,
)
from app.services.updater import RefreshOrchestrator
from app.services.scheduler import reschedule_provider, remove_provider_schedule
from app.repositories.settings_repo import get_settings, update_settings

bp = Blueprint("api", __name__)

VALID_SCHEDULE_TYPES = {"disabled", "monthly", "weekly", "daily", "interval"}
VALID_UA_MODES = {"auto", "ClashMeta", "clash-verge/v2.4.2", "ClashForWindows/0.20.39", "Clash", "browser"}
MAX_NAME_LENGTH = 128
MAX_INTERVAL_HOURS = 168


@bp.route("/providers", methods=["GET"])
def api_list_providers():
    providers = list_providers()
    return jsonify([p.to_dict(include_source_url=True) for p in providers])


@bp.route("/providers", methods=["POST"])
def api_create_provider():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    errors = {}
    if not data.get("name"):
        errors["name"] = ["Name is required"]
    elif len(data["name"]) > MAX_NAME_LENGTH:
        errors["name"] = [f"Name must be at most {MAX_NAME_LENGTH} characters"]

    if not data.get("source_url"):
        errors["source_url"] = ["Source URL is required"]
    else:
        parsed = urlparse(data["source_url"])
        if parsed.scheme not in ("http", "https"):
            errors["source_url"] = ["Source URL must use http or https scheme"]
        if not parsed.hostname:
            errors["source_url"] = ["Source URL must have a valid hostname"]

    schedule = data.get("schedule", {"type": "disabled"})
    schedule_type = schedule.get("type", "disabled")
    if schedule_type not in VALID_SCHEDULE_TYPES:
        errors["schedule"] = [f"Invalid schedule type. Must be one of: {', '.join(sorted(VALID_SCHEDULE_TYPES))}"]
    elif schedule_type == "interval":
        hours = schedule.get("interval_hours", 24)
        if not isinstance(hours, (int, float)) or not (1 <= hours <= MAX_INTERVAL_HOURS):
            errors["schedule"] = [f"interval_hours must be between 1 and {MAX_INTERVAL_HOURS}"]
    elif schedule_type == "monthly":
        dom = schedule.get("day_of_month", 1)
        if not isinstance(dom, int) or not (1 <= dom <= 31):
            errors["schedule"] = ["day_of_month must be between 1 and 31"]
    elif schedule_type == "weekly":
        dow = schedule.get("day_of_week", 0)
        if not isinstance(dow, int) or not (0 <= dow <= 6):
            errors["schedule"] = ["day_of_week must be between 0 (Monday) and 6 (Sunday)"]

    if errors:
        return jsonify(error="validation", details=errors), 400

    ua_mode = data.get("ua_mode", "auto")
    if ua_mode not in VALID_UA_MODES:
        return jsonify(error="validation", details={"ua_mode": [f"Invalid UA mode. Must be one of: {', '.join(sorted(VALID_UA_MODES))}"]}), 400

    provider = create_provider(
        name=data["name"],
        source_url=data["source_url"],
        schedule=schedule,
        ua_mode=ua_mode,
    )

    reschedule_provider(provider)

    orch = RefreshOrchestrator(current_app._get_current_object())
    threading.Thread(
        target=orch.refresh,
        args=(provider.id,),
        kwargs={"trigger": "manual"},
        daemon=True,
    ).start()

    return jsonify(provider.to_dict(include_source_url=True)), 201


@bp.route("/providers/<int:provider_id>", methods=["PATCH"])
def api_update_provider(provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return jsonify(error="Provider not found"), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify(error="Invalid JSON"), 400

    errors = {}
    if "name" in data:
        if not data["name"]:
            errors["name"] = ["Name cannot be empty"]
        elif len(data["name"]) > MAX_NAME_LENGTH:
            errors["name"] = [f"Name must be at most {MAX_NAME_LENGTH} characters"]

    if "source_url" in data:
        parsed = urlparse(data["source_url"])
        if parsed.scheme not in ("http", "https"):
            errors["source_url"] = ["Source URL must use http or https scheme"]
        if not parsed.hostname:
            errors["source_url"] = ["Source URL must have a valid hostname"]

    if "schedule" in data:
        s = data["schedule"]
        st = s.get("type", provider.schedule_type)
        if st not in VALID_SCHEDULE_TYPES:
            errors["schedule"] = [f"Invalid schedule type. Must be one of: {', '.join(sorted(VALID_SCHEDULE_TYPES))}"]
        elif st == "interval":
            hours = s.get("interval_hours", 24)
            if not isinstance(hours, (int, float)) or not (1 <= hours <= MAX_INTERVAL_HOURS):
                errors["schedule"] = [f"interval_hours must be between 1 and {MAX_INTERVAL_HOURS}"]
        elif st == "monthly":
            dom = s.get("day_of_month", 1)
            if not isinstance(dom, int) or not (1 <= dom <= 31):
                errors["schedule"] = ["day_of_month must be between 1 and 31"]
        elif st == "weekly":
            dow = s.get("day_of_week", 0)
            if not isinstance(dow, int) or not (0 <= dow <= 6):
                errors["schedule"] = ["day_of_week must be between 0 (Monday) and 6 (Sunday)"]

    if "ua_mode" in data:
        if data["ua_mode"] not in VALID_UA_MODES:
            errors["ua_mode"] = [f"Invalid UA mode. Must be one of: {', '.join(sorted(VALID_UA_MODES))}"]

    if errors:
        return jsonify(error="validation", details=errors), 400

    update_provider(provider, data)
    reschedule_provider(provider)
    return jsonify(provider.to_dict(include_source_url=True))


@bp.route("/providers/<int:provider_id>", methods=["DELETE"])
def api_delete_provider(provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return jsonify(error="Provider not found"), 404

    from app.services.version_store import VersionStore
    vs = VersionStore(
        subscriptions_dir=current_app.config["SUBSCRIPTIONS_DIR"],
        retention_count=current_app.config["VERSION_RETENTION_COUNT"],
    )
    vs.delete_provider_files(provider_id, provider.name)
    delete_provider(provider)
    remove_provider_schedule(provider_id)
    return jsonify(status="deleted")


@bp.route("/providers/<int:provider_id>/refresh", methods=["POST"])
def api_refresh_provider(provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return jsonify(error="Provider not found"), 404

    orch = RefreshOrchestrator(current_app._get_current_object())
    threading.Thread(
        target=orch.refresh,
        args=(provider.id,),
        kwargs={"trigger": "manual"},
        daemon=True,
    ).start()

    return jsonify(status="refreshing")


@bp.route("/providers/<int:provider_id>/rotate", methods=["POST"])
def api_rotate_provider(provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return jsonify(error="Provider not found"), 404

    provider.rotate_token()
    db.session.commit()
    return jsonify(
        status="rotated",
        public_token=provider.public_token,
    )


@bp.route("/update-runs", methods=["GET"])
def api_list_update_runs():
    provider_id = request.args.get("provider_id", type=int)
    runs = list_update_runs(provider_id=provider_id)
    return jsonify([r.to_dict() for r in runs])


@bp.route("/logs", methods=["GET"])
def api_list_logs():
    log_store = current_app.extensions.get("log_store") if hasattr(current_app, "extensions") else None
    if log_store is None:
        return jsonify(entries=[])
    provider_id = request.args.get("provider_id", type=int)
    limit = request.args.get("limit", default=200, type=int)
    if limit is None or limit <= 0 or limit > 1000:
        limit = 200
    entries = log_store.entries(provider_id=provider_id, limit=limit)
    return jsonify(entries=entries)


@bp.route("/logs/clear", methods=["POST"])
def api_clear_logs():
    log_store = current_app.extensions.get("log_store") if hasattr(current_app, "extensions") else None
    if log_store is None:
        return jsonify(cleared=0)
    cleared = log_store.clear()
    return jsonify(cleared=cleared)


@bp.route("/logs/export", methods=["GET"])
def api_export_logs():
    """Download the full retained log history as a JSONL file attachment."""
    log_store = current_app.extensions.get("log_store") if hasattr(current_app, "extensions") else None
    text = log_store.export_text() if log_store is not None else ""
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"converter-logs-{stamp}.jsonl"
    resp = Response(text, mimetype="application/x-ndjson")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store"
    return resp



def _rebuild_log_sink(app):
    """Build a fresh LogSink from the live settings row and replace it."""
    from app.services.log_sink import LogSink
    s = get_settings()
    new_sink = LogSink(
        host=s.rsyslog_host,
        port=s.rsyslog_port,
        proto=s.rsyslog_proto,
        facility=s.rsyslog_facility,
    )
    old = app.extensions.get("log_sink") if hasattr(app, "extensions") else None
    if old is not None:
        try:
            old.close()
        except Exception:
            pass
    app.extensions["log_sink"] = new_sink


@bp.route("/settings", methods=["GET"])
def api_get_settings():
    s = get_settings()
    return jsonify(s.to_dict())


@bp.route("/settings", methods=["PATCH"])
def api_update_settings():
    data = request.get_json(silent=True) or {}
    try:
        s = update_settings(**data)
    except ValueError as e:
        return jsonify(error="validation", details={"_": [str(e)]}), 400
    app = current_app._get_current_object()
    _rebuild_log_sink(app)
    return jsonify(s.to_dict())

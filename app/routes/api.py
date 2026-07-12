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

bp = Blueprint("api", __name__)

VALID_SCHEDULE_TYPES = {"disabled", "monthly", "weekly", "daily", "interval"}
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

    provider = create_provider(
        name=data["name"],
        source_url=data["source_url"],
        schedule=schedule,
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
    vs.delete_provider_files(provider_id)
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

import json
import queue
import threading

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

bp = Blueprint("api", __name__)


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
    if not data.get("source_url"):
        errors["source_url"] = ["Source URL is required"]
    if errors:
        return jsonify(error="validation", details=errors), 400

    schedule = data.get("schedule", {"type": "disabled"})
    provider = create_provider(
        name=data["name"],
        source_url=data["source_url"],
        schedule=schedule,
    )

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

    update_provider(provider, data)
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

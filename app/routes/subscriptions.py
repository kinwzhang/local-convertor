from datetime import datetime, timezone

from flask import Blueprint, abort, make_response, current_app

from app.repositories.provider_repo import get_provider_by_token
from app.services.version_store import VersionStore
from app.services.updater import RefreshOrchestrator

bp = Blueprint("subscriptions", __name__)


@bp.route("/subscriptions/<token>", methods=["GET", "HEAD"])
def serve_subscription(token):
    provider = get_provider_by_token(token)
    if not provider:
        abort(404)

    orch = RefreshOrchestrator(current_app._get_current_object())

    was_fresh = orch.is_fresh(provider.id)
    if not was_fresh:
        orch.refresh(provider.id, trigger="request")

    vs = VersionStore(
        subscriptions_dir=current_app.config["SUBSCRIPTIONS_DIR"],
        retention_count=current_app.config["VERSION_RETENTION_COUNT"],
    )

    content = vs.get_current(provider.id)
    if content is None:
        resp = make_response("No subscription data available", 503)
        resp.content_type = "text/plain; charset=utf-8"
        return resp

    content_hash = vs.get_current_hash(provider.id)
    resp = make_response(content, 200)
    resp.content_type = "text/plain; charset=utf-8"
    resp.headers["ETag"] = f'"{content_hash}"'
    resp.headers["Cache-Control"] = "no-cache"

    if provider.last_success_at:
        resp.headers["Last-Modified"] = provider.last_success_at.strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

    if not was_fresh and provider.last_error:
        resp.headers["Warning"] = '299 - "Stale data served due to fetch failure"'
        resp.headers["X-Subscription-Stale"] = "true"

    return resp

import logging
from datetime import datetime, timezone

from flask import Blueprint, abort, make_response, current_app, request

from app.repositories.provider_repo import get_provider_by_token
from app.services.version_store import VersionStore
from app.services.updater import RefreshOrchestrator
from app.routes.events import publish_event

logger = logging.getLogger(__name__)

bp = Blueprint("subscriptions", __name__)


def _emit_query_log(app, event_type, fields):
    """Mirror the updater's hook: append + rsyslog-sink for query events."""
    log_store = app.extensions.get("log_store") if hasattr(app, "extensions") else None
    log_sink = app.extensions.get("log_sink") if hasattr(app, "extensions") else None
    payload = {**fields, "event": event_type}
    if log_store is not None:
        try:
            log_store.append(payload)
        except Exception:  # pragma: no cover
            logger.exception("log_store.append failed on subscription query")
    if log_sink is not None:
        try:
            log_sink.emit(event_type, **payload)
        except Exception:  # pragma: no cover
            logger.exception("log_sink.emit failed on subscription query")


def _client_ip():
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    return client_ip


@bp.route("/subscriptions/<token>", methods=["GET", "HEAD"])
def serve_subscription(token):
    app = current_app._get_current_object()
    provider = get_provider_by_token(token)
    if not provider:
        abort(404)

    client_ip = _client_ip()

    orch = RefreshOrchestrator(app)

    was_fresh = orch.is_fresh(provider.id)
    if not was_fresh:
        orch.refresh(provider.id, trigger="request")
        provider = get_provider_by_token(token)

    vs = VersionStore(
        subscriptions_dir=app.config["SUBSCRIPTIONS_DIR"],
        retention_count=app.config["VERSION_RETENTION_COUNT"],
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

    status = "stale" if (not was_fresh and provider.last_error) else "served"
    logger.info(
        "Subscription %s from %s [%s]",
        provider.name, client_ip, status,
    )
    publish_event({
        "provider_id": provider.id,
        "run_id": None,
        "provider_name": provider.name,
        "trigger": "request",
        "stage": "served",
        "status": "success",
        "message": f"Client {client_ip} — {status}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    })
    event_type = "subscription.stale" if status == "stale" else "subscription.served"
    _emit_query_log(app, event_type, {
        "run_id": None,
        "provider_id": provider.id,
        "provider_name": provider.name,
        "trigger": "request",
        "status": "success" if status == "served" else "warning",
        "client_ip": client_ip,
        "message": f"Client {client_ip} — {status}",
    })

    return resp

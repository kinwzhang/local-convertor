import atexit
import os

from flask import Flask, jsonify

from app.extensions import db, migrate


def create_app(config_class=None):
    from app.config import Config

    app = Flask(__name__)
    app.config.from_object(config_class or Config)

    os.makedirs(app.config["DATABASE_DIR"], exist_ok=True)
    os.makedirs(app.config["SUBSCRIPTIONS_DIR"], exist_ok=True)
    os.makedirs(app.config.get("LOGS_DIR", os.path.join(app.config["DATA_DIR"], "logs")), exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    _configure_logging(app)
    _init_settings(app)
    _configure_log_sinks(app)

    # Migrate legacy on-disk subscription files into the new `<slug>-<id>/`
    # directory + `<iter>_raw.yaml` naming scheme, then update DB paths.
    # Idempotent — runs once per provider per session.
    try:
        from app.services.version_store import migrate_naming
        migrate_naming(app)
    except Exception:
        # The migration is best-effort at boot; providers that have never
        # been refreshed yet have nothing to migrate. Still log so future
        # debugging has breadcrumbs.
        import logging
        logging.getLogger(__name__).exception("Subscription naming migration failed")

    from app.services.scheduler import init_scheduler
    init_scheduler(app)

    from app.routes import ui, api, subscriptions, events

    app.register_blueprint(ui.bp)
    app.register_blueprint(api.bp, url_prefix="/api")
    app.register_blueprint(subscriptions.bp)
    app.register_blueprint(events.bp, url_prefix="/api")

    @app.route("/health")
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))
            db_status = "ok"
            status_code = 200
        except Exception:
            db_status = "unavailable"
            status_code = 503
        return jsonify(status="ok", database=db_status), status_code

    return app


def _configure_logging(app):
    import logging

    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _table_exists(app, name):
    """Cheap helper: does `name` exist in the bound DB? Tolerates a missing engine."""
    try:
        engine = app.extensions["db"].engine
        with engine.connect() as conn:
            return engine.dialect.has_table(conn, name)
    except Exception:
        return False


def _configure_log_sinks(app):
    """Build LogStore + LogSink and stash them on `app.extensions`.

    LogSink reads from AppSettings when the table exists; otherwise it
    falls back to env-var defaults so the conftest (no `db.create_all`
    yet) and a fresh dev install without a migration still boot.
    """
    from app.services.log_store import LogStore
    from app.services.log_sink import LogSink

    log_store = LogStore(app.config["LOGS_DIR"])

    if _table_exists(app, "app_settings"):
        from app.repositories.settings_repo import get_settings
        with app.app_context():
            s = get_settings()
            log_sink = LogSink(
                host=s.rsyslog_host,
                port=s.rsyslog_port,
                proto=s.rsyslog_proto,
                facility=s.rsyslog_facility,
            )
    else:
        log_sink = LogSink(
            host=app.config.get("RSYSLOG_HOST"),
            port=app.config.get("RSYSLOG_PORT"),
            proto=app.config.get("RSYSLOG_PROTO"),
            facility=app.config.get("RSYSLOG_FACILITY"),
        )

    app.extensions["log_store"] = log_store
    app.extensions["log_sink"] = log_sink

    atexit.register(_close_sinks, app)


def _close_sinks(app):
    log_sink = app.extensions.get("log_sink") if hasattr(app, "extensions") else None
    if log_sink is not None:
        try:
            log_sink.close()
        except Exception:
            pass


def _init_settings(app):
    """Bootstrap the AppSettings singleton row from env vars on first run.

    Skips silently if the table doesn't exist yet (e.g. test conftest where
    `db.create_all()` hasn't run). Operationally, the operator must run
    `flask db upgrade` before starting the app — that's documented in
    `CLAUDE.md`. After upgrade, env-var defaults are persisted into the row
    only if the operator hasn't already saved via the UI.
    """
    if not _table_exists(app, "app_settings"):
        return
    from app.repositories.settings_repo import get_settings, update_settings

    with app.app_context():
        s = get_settings()
        env_host = app.config.get("RSYSLOG_HOST")
        if env_host and not s.rsyslog_host:
            update_settings(rsyslog_host=env_host)

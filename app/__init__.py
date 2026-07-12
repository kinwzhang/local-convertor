import os

from flask import Flask, jsonify

from app.extensions import db, migrate


def create_app(config_class=None):
    from app.config import Config

    app = Flask(__name__)
    app.config.from_object(config_class or Config)

    os.makedirs(app.config["DATABASE_DIR"], exist_ok=True)
    os.makedirs(app.config["SUBSCRIPTIONS_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    _configure_logging(app)

    from app.services.scheduler import init_scheduler
    init_scheduler(app)

    from app.routes import ui, api, subscriptions, events

    app.register_blueprint(ui.bp)
    app.register_blueprint(api.bp, url_prefix="/api")
    app.register_blueprint(subscriptions.bp)
    app.register_blueprint(events.bp, url_prefix="/api")

    @app.route("/health")
    def health():
        return jsonify(status="ok"), 200

    return app


def _configure_logging(app):
    import logging

    level = getattr(logging, app.config.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

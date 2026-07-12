import os
import tempfile

from tests.conftest import TestConfig


def test_health_endpoint(app):
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"


def test_health_reports_db_failure(app, monkeypatch):
    from app.extensions import db

    original_execute = db.session.execute

    def failing_execute(*args, **kwargs):
        raise RuntimeError("DB connection lost")

    monkeypatch.setattr(db.session, "execute", failing_execute)
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 503
    data = response.get_json()
    assert data["database"] == "unavailable"


def test_index_loads(app):
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Local Clash" in response.data


def test_clean_volume_db_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "database"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "subscriptions"), exist_ok=True)

        class CleanConfig:
            TESTING = True
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(tmpdir, 'database', 'app.db')}"
            DATA_DIR = tmpdir
            SUBSCRIPTIONS_DIR = os.path.join(tmpdir, "subscriptions")
            DATABASE_DIR = os.path.join(tmpdir, "database")
            REQUEST_TIMEOUT = 30
            MAX_RESPONSE_SIZE = 10 * 1024 * 1024
            FRESHNESS_THRESHOLD_HOURS = 3
            VERSION_RETENTION_COUNT = 5
            TRUSTED_HOSTS = []

        from app import create_app
        from app.extensions import db as _db

        application = create_app(config_class=CleanConfig)
        with application.app_context():
            from app.models.provider import Provider, SubscriptionVersion, UpdateRun  # noqa: F401

            _db.create_all()
            from sqlalchemy import inspect
            inspector = inspect(_db.engine)
            assert "providers" in inspector.get_table_names()
            assert "subscription_versions" in inspector.get_table_names()
            assert "update_runs" in inspector.get_table_names()

            client = application.test_client()
            response = client.get("/health")
            assert response.status_code == 200
            assert response.get_json()["database"] == "ok"

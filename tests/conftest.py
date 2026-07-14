import pytest

from app import create_app
from app.extensions import db as _db


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DATA_DIR = "/tmp/test_local_convertor"
    SUBSCRIPTIONS_DIR = "/tmp/test_local_convertor/subscriptions"
    DATABASE_DIR = "/tmp/test_local_convertor/database"
    LOGS_DIR = "/tmp/test_local_convertor/logs"
    REQUEST_TIMEOUT = 30
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024
    FRESHNESS_THRESHOLD_HOURS = 3
    VERSION_RETENTION_COUNT = 5
    LOG_RETENTION_DAYS = 7
    TRUSTED_HOSTS = []
    # rsyslog — disabled by default in tests.
    RSYSLOG_HOST = None
    RSYSLOG_PORT = 514
    RSYSLOG_PROTO = "tcp"
    RSYSLOG_FACILITY = "local0"


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    # Per-session tmp directories so parallel test runs don't collide
    # on the global /tmp paths baked into TestConfig.
    base = tmp_path_factory.mktemp("local_convertor")
    TestConfig.DATA_DIR = str(base)
    TestConfig.SUBSCRIPTIONS_DIR = str(base / "subscriptions")
    TestConfig.DATABASE_DIR = str(base / "database")
    TestConfig.LOGS_DIR = str(base / "logs")

    application = create_app(config_class=TestConfig)
    with application.app_context():
        # Import every SQLAlchemy model so `db.create_all()` includes its
        # table. The settings model was added after the original fixture.
        from app.models.provider import Provider, SubscriptionVersion, UpdateRun  # noqa: F401
        from app.models.settings import AppSettings  # noqa: F401

        _db.create_all()
        # Seed the AppSettings singleton so `get_settings()` in `_init_settings`
        # and `_configure_log_sinks` find a row in test sessions without a
        # migration step.
        if _db.session.query(AppSettings).first() is None:
            _db.session.add(AppSettings(id=1))
            _db.session.commit()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.session.rollback()
        yield _db


@pytest.fixture(autouse=True)
def _clear_log_store(app):
    """Reset the JSONL log between tests so they don't see each other's entries."""
    log_store = app.extensions.get("log_store") if hasattr(app, "extensions") else None
    if log_store is not None:
        log_store.clear()
    yield
    if log_store is not None:
        log_store.clear()

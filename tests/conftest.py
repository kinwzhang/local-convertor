import pytest

from app import create_app
from app.extensions import db as _db


class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DATA_DIR = "/tmp/test_local_convertor"
    SUBSCRIPTIONS_DIR = "/tmp/test_local_convertor/subscriptions"
    DATABASE_DIR = "/tmp/test_local_convertor/database"
    REQUEST_TIMEOUT = 30
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024
    FRESHNESS_THRESHOLD_HOURS = 3
    VERSION_RETENTION_COUNT = 5
    TRUSTED_HOSTS = []


@pytest.fixture(scope="session")
def app():
    application = create_app(config_class=TestConfig)
    with application.app_context():
        from app.models.provider import Provider, SubscriptionVersion, UpdateRun  # noqa: F401

        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.session.rollback()
        yield _db

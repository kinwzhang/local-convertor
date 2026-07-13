import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))

    DATABASE_DIR = os.path.join(DATA_DIR, "database")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(DATABASE_DIR, 'app.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SUBSCRIPTIONS_DIR = os.path.join(DATA_DIR, "subscriptions")

    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://10.8.6.13:5000")
    BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
    BIND_PORT = int(os.environ.get("BIND_PORT", "5000"))

    TIMEZONE = os.environ.get("TIMEZONE", "Asia/Hong_Kong")

    REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))
    MAX_RESPONSE_SIZE = int(os.environ.get("MAX_RESPONSE_SIZE", str(10 * 1024 * 1024)))
    FRESHNESS_THRESHOLD_HOURS = int(os.environ.get("FRESHNESS_THRESHOLD_HOURS", "3"))
    VERSION_RETENTION_COUNT = int(os.environ.get("VERSION_RETENTION_COUNT", "5"))

    TRUSTED_HOSTS: list[str] = os.environ.get("TRUSTED_HOSTS", "").split(",") if os.environ.get("TRUSTED_HOSTS") else []

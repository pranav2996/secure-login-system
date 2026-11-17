import os
from datetime import timedelta

from sqlalchemy.engine import URL, make_url


def normalize_database_url(database_url, *, require_ssl=False):
    """Normalize PostgreSQL URLs for psycopg 3 and enforce TLS without logging credentials."""
    if not database_url:
        return database_url
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]

    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        return url.render_as_string(hide_password=False)

    query = dict(url.query)
    if require_ssl and query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        query["sslmode"] = "require"
    return url.set(drivername="postgresql+psycopg", query=query).render_as_string(hide_password=False)


def database_settings(database_url, *, production=False, database_path=""):
    """Return a SQLAlchemy URI and a small, health-checked engine configuration."""
    if database_url:
        uri = normalize_database_url(database_url, require_ssl=production)
    elif database_path:
        uri = URL.create("sqlite", database=database_path).render_as_string(hide_password=False)
    else:
        uri = "sqlite:///secure_login.db"

    backend = make_url(uri).get_backend_name()
    if backend == "postgresql":
        engine_options = {
            "pool_size": 1,
            "max_overflow": 0,
            "pool_timeout": 30,
            "pool_recycle": 240,
            "pool_pre_ping": True,
            "connect_args": {"connect_timeout": 30, "prepare_threshold": None},
        }
    elif backend == "sqlite":
        engine_options = {
            "pool_pre_ping": True,
            "connect_args": {"timeout": 30},
        }
    else:
        raise ValueError("Only SQLite and PostgreSQL database URLs are supported.")
    return uri, engine_options


class Config:
    MAX_CONTENT_LENGTH = 16 * 1024
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    APP_ENV = os.environ.get("APP_ENV", "development").lower()
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "")
    SQLALCHEMY_DATABASE_URI, SQLALCHEMY_ENGINE_OPTIONS = database_settings(
        DATABASE_URL,
        production=APP_ENV == "production",
        database_path=DATABASE_PATH,
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = (
        APP_ENV == "production"
        or os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    )
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_REFRESH_EACH_REQUEST = True
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    TRUST_PROXY = APP_ENV == "production" or os.environ.get("TRUST_PROXY", "false").lower() == "true"
    PREFERRED_URL_SCHEME = "https" if APP_ENV == "production" else "http"

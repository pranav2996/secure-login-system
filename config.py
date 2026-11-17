import os
from datetime import timedelta

from sqlalchemy.engine import URL


def database_uri():
    """Build a SQLite URI from DATABASE_PATH, keeping DATABASE_URL compatible."""
    database_path = os.environ.get("DATABASE_PATH")
    if database_path:
        return URL.create("sqlite", database=database_path).render_as_string(hide_password=False)
    return os.environ.get("DATABASE_URL", "sqlite:///secure_login.db")


class Config:
    MAX_CONTENT_LENGTH = 16 * 1024
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    APP_ENV = os.environ.get("APP_ENV", "development").lower()
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "")
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}
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
    RATELIMIT_STORAGE_URI = "memory://"
    TRUST_PROXY = APP_ENV == "production" or os.environ.get("TRUST_PROXY", "false").lower() == "true"
    MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "false").lower() == "true"
    ALLOW_DATABASE_INIT = os.environ.get("ALLOW_DATABASE_INIT", "false").lower() == "true"
    PREFERRED_URL_SCHEME = "https" if APP_ENV == "production" else "http"

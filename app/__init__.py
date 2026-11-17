import os
import secrets
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, request, session, url_for
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

from .extensions import csrf, db, limiter


def create_app(test_config=None):
    load_dotenv()
    from config import Config
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config.setdefault("MAX_CONTENT_LENGTH", 16 * 1024)
    if test_config:
        app.config.update(test_config)
    if app.config.get("APP_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["PREFERRED_URL_SCHEME"] = "https"
        app.config["TRUST_PROXY"] = True
    if app.config.get("TRUST_PROXY"):
        # Render terminates TLS and forwards the original client scheme/IP.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    if app.config.get("APP_ENV") == "production":
        database_path = app.config.get("DATABASE_PATH")
        if not database_path or not os.path.isabs(database_path):
            raise RuntimeError("Set DATABASE_PATH to an absolute path on Render's persistent disk.")
        if app.config.get("ALLOW_DATABASE_INIT") and not app.config.get("MAINTENANCE_MODE"):
            raise RuntimeError("ALLOW_DATABASE_INIT is only permitted while MAINTENANCE_MODE is enabled.")
        if not os.path.isfile(database_path) and not (
            app.config.get("ALLOW_DATABASE_INIT") and app.config.get("MAINTENANCE_MODE")
        ):
            raise RuntimeError(
                "Production database file is missing. Restore a verified database copy to the persistent disk first."
            )
    if not app.config.get("SECRET_KEY"):
        if not app.testing:
            raise RuntimeError("Set SECRET_KEY in your .env file before starting the app.")
        app.config["SECRET_KEY"] = "test-only-secret"
    if not app.config.get("ENCRYPTION_KEY"):
        if not app.testing:
            raise RuntimeError("Set ENCRYPTION_KEY in your .env file before starting the app.")
        app.config["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    try:
        app.extensions["totp_fernet"] = Fernet(app.config["ENCRYPTION_KEY"].encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError("ENCRYPTION_KEY must be a valid Fernet key.") from exc

    os.makedirs(app.instance_path, exist_ok=True)
    configured_db_path = app.config.get("DATABASE_PATH")
    if configured_db_path:
        os.makedirs(os.path.dirname(os.path.abspath(configured_db_path)), exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.security import security_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(security_bp)

    @app.get("/healthz")
    def healthz():
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok")

    @app.before_request
    def maintenance_mode():
        if app.config.get("MAINTENANCE_MODE") and request.endpoint != "healthz":
            return "Temporarily unavailable for database maintenance.", 503

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.endpoint in {"dashboard.index", "security.enable_2fa", "security.disable_2fa", "security.show_recovery_codes"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.errorhandler(429)
    def rate_limited(_error):
        flash("Too many attempts. Please wait a few minutes and try again.", "error")
        return redirect(url_for("auth.login")), 429

    with app.app_context():
        db.create_all()
        if "pending_totp_secret" not in {column["name"] for column in inspect(db.engine).get_columns("user")}:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE user ADD COLUMN pending_totp_secret BLOB"))
    return app

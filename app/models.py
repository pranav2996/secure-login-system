from datetime import datetime, timezone

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.LargeBinary(60), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_2fa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    totp_secret = db.Column(db.LargeBinary, nullable=True)
    pending_totp_secret = db.Column(db.LargeBinary, nullable=True)
    recovery_codes_hash = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    last_login = db.Column(db.DateTime(timezone=True), nullable=True)

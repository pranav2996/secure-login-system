import re
import secrets
from datetime import datetime, timezone

import bcrypt
import pyotp
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_

from ..extensions import db, limiter
from ..models import User

auth_bp = Blueprint("auth", __name__)


def valid_password(value):
    return (len(value) >= 8 and len(value) <= 72 and re.search(r"[A-Za-z]", value)
            and re.search(r"\d", value) and re.search(r"[^A-Za-z0-9]", value))


@auth_bp.route("/")
def home():
    return redirect(url_for("dashboard.index" if session.get("user_id") else "auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = []
        if not full_name or len(full_name) > 120 or any(ord(c) < 32 and c not in "\t" for c in full_name): errors.append("Enter your full name (up to 120 characters).")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username): errors.append("Username must be 3–32 characters: letters, numbers, dots, dashes, or underscores.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254: errors.append("Enter a valid email address.")
        if not valid_password(password): errors.append("Password must be 8–72 characters and include a letter, a number, and a symbol.")
        if password != confirm: errors.append("Passwords do not match.")
        if username and db.session.scalar(db.select(User.id).where(func.lower(User.username) == username.lower())): errors.append("That username is already in use.")
        if email and db.session.scalar(db.select(User.id).where(func.lower(User.email) == email)): errors.append("That email is already registered.")
        if errors:
            for error in errors: flash(error, "error")
            return render_template("register.html")
        try:
            user = User(full_name=full_name, username=username, email=email,
                        password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)))
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("We could not create your account. Check your details and try again.", "error")
            return render_template("register.html"), 400
        flash("Your account is ready. Sign in to continue.", "success")
        return redirect(url_for("auth.login"))
    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(User).where(or_(func.lower(User.username) == identity.lower(), func.lower(User.email) == identity.lower()))) if identity and len(identity) <= 254 else None
        password_ok = False
        if user and isinstance(password, str) and 0 < len(password.encode()) <= 72:
            try:
                password_ok = bcrypt.checkpw(password.encode(), user.password_hash)
            except (ValueError, TypeError):
                password_ok = False
        if not user or not user.is_active or not password_ok:
            flash("Invalid username/email or password.", "error")
            return render_template("login.html"), 401
        session.clear()
        if user.is_2fa_enabled:
            session["pending_2fa_user_id"] = user.id
            session.permanent = True
            return redirect(url_for("auth.verify_2fa"))
        session["user_id"] = user.id
        session.permanent = True
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@auth_bp.route("/verify-2fa", methods=["GET", "POST"])
@limiter.limit("8 per minute")
def verify_2fa():
    user = db.session.get(User, session.get("pending_2fa_user_id"))
    if not user or not user.is_active or not user.is_2fa_enabled:
        session.clear()
        flash("Please sign in again.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        code = request.form.get("code", "").strip().replace(" ", "")
        valid = bool(user.totp_secret and pyotp.TOTP(current_app.extensions["totp_fernet"].decrypt(user.totp_secret).decode()).verify(code, valid_window=1)) if code else False
        if not valid:
            candidate = code.upper().replace("-", "")
            for i, digest in enumerate(user.recovery_codes_hash or []):
                if bcrypt.checkpw(candidate.encode(), digest.encode()):
                    codes = list(user.recovery_codes_hash)
                    codes.pop(i)
                    user.recovery_codes_hash = codes
                    db.session.commit()
                    valid = True
                    flash("A recovery code was used. Remaining recovery codes: " + str(len(codes)), "success")
                    break
        if not valid:
            flash("That verification code was not accepted.", "error")
            return render_template("verify_2fa.html"), 401
        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        return redirect(url_for("dashboard.index"))
    return render_template("verify_2fa.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))

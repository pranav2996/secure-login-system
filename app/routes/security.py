import secrets
import string
from io import BytesIO
import base64

import bcrypt
import pyotp
import qrcode
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from ..extensions import db
from ..models import User
from .dashboard import login_required

security_bp = Blueprint("security", __name__)


@security_bp.route("/security/2fa/enable", methods=["GET", "POST"])
@login_required
def enable_2fa(user):
    if user.is_2fa_enabled:
        return redirect(url_for("dashboard.index"))
    secret = current_app.extensions["totp_fernet"].decrypt(user.pending_totp_secret).decode() if user.pending_totp_secret else pyotp.random_base32()
    if not user.pending_totp_secret:
        user.pending_totp_secret = current_app.extensions["totp_fernet"].encrypt(secret.encode())
        db.session.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Secure Login System")
    qr = qrcode.make(uri)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_data = base64.b64encode(buffer.getvalue()).decode()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            flash("That code was not accepted. Check your authenticator and try again.", "error")
            return render_template("enable_2fa.html", qr_data=qr_data), 400
        codes = ["".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12)) for _ in range(8)]
        user.recovery_codes_hash = [bcrypt.hashpw(c.encode(), bcrypt.gensalt(rounds=12)).decode() for c in codes]
        user.totp_secret = user.pending_totp_secret
        user.pending_totp_secret = None
        user.is_2fa_enabled = True
        db.session.commit()
        flash("Two-factor authentication is enabled. Save these recovery codes now.", "success")
        return render_template("recovery_codes.html", codes=codes)
    return render_template("enable_2fa.html", qr_data=qr_data)


@security_bp.route("/security/2fa/disable", methods=["POST"])
@login_required
def disable_2fa(user):
    code = request.form.get("code", "").strip()
    password = request.form.get("password", "")
    if not bcrypt.checkpw(password.encode(), user.password_hash):
        flash("Password was not accepted.", "error")
        return redirect(url_for("dashboard.index"))
    valid = False
    if user.totp_secret:
        secret = current_app.extensions["totp_fernet"].decrypt(user.totp_secret).decode()
        valid = pyotp.TOTP(secret).verify(code, valid_window=1)
    if not valid:
        flash("Enter a current authenticator code to disable two-factor authentication.", "error")
        return redirect(url_for("dashboard.index"))
    user.is_2fa_enabled = False
    user.totp_secret = None
    user.pending_totp_secret = None
    user.recovery_codes_hash = []
    db.session.commit()
    flash("Two-factor authentication has been disabled.", "success")
    return redirect(url_for("dashboard.index"))

import re
import bcrypt
import pyotp
from app.extensions import db
from app.models import User
from .conftest import login, register


def test_csrf_protection_enabled_for_real_app(tmp_path):
    from app import create_app
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'csrf.db'}"})
    response = app.test_client().post("/login", data={"identity":"x", "password":"x"})
    assert response.status_code == 400


def test_login_rate_limit(client):
    codes = [client.post("/login", data={"identity":"nobody", "password":"bad"}).status_code for _ in range(7)]
    assert 429 in codes


def secret_for(app):
    with app.app_context():
        user = db.session.scalar(db.select(User))
        token = user.totp_secret or user.pending_totp_secret
        return app.extensions["totp_fernet"].decrypt(token).decode()


def test_back_to_sign_in_is_a_get_link(client, app):
    register(client)
    login(client)
    client.get("/security/2fa/enable")
    secret = secret_for(app)
    client.post("/security/2fa/enable", data={"code":pyotp.TOTP(secret).now()})
    client.post("/logout")
    client.post("/login", data={"identity":"sample_user", "password":"Passw0rd!"})

    verify_response = client.get("/verify-2fa")
    assert verify_response.status_code == 200
    assert b'href="/login"' in verify_response.data
    assert b"logout-form" not in verify_response.data
    assert b"event.preventDefault()" not in verify_response.data

    login_response = client.get("/login")
    assert login_response.status_code == 200
    assert client.put("/login").status_code == 405


def test_totp_enrollment_and_login(client, app):
    register(client)
    login(client)
    assert client.get("/security/2fa/enable").status_code == 200
    secret = secret_for(app)
    response = client.post("/security/2fa/enable", data={"code":pyotp.TOTP(secret).now()})
    assert b"recovery codes" in response.data.lower()
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert user.is_2fa_enabled and len(user.recovery_codes_hash) == 8
        assert user.totp_secret != secret.encode()
    client.post("/logout")
    assert "/verify-2fa" in client.post("/login", data={"identity":"sample_user", "password":"Passw0rd!"}).location
    code = pyotp.TOTP(secret_for(app)).now()
    assert b"Welcome, Sample" in client.post("/verify-2fa", data={"code":code}, follow_redirects=True).data


def test_bad_totp_setup_rejected(client):
    register(client)
    login(client)
    client.get("/security/2fa/enable")
    assert client.post("/security/2fa/enable", data={"code":"000000"}).status_code == 400


def test_recovery_code_is_consumed_once(client, app):
    register(client)
    login(client)
    client.get("/security/2fa/enable")
    secret = secret_for(app)
    response = client.post("/security/2fa/enable", data={"code":pyotp.TOTP(secret).now()})
    code = re.findall(rb"<code>([^<]+)</code>", response.data)[0].decode()
    client.post("/logout")
    client.post("/login", data={"identity":"sample_user", "password":"Passw0rd!"})
    assert client.post("/verify-2fa", data={"code":code}, follow_redirects=True).status_code == 200
    client.post("/logout")
    client.post("/login", data={"identity":"sample_user", "password":"Passw0rd!"})
    assert client.post("/verify-2fa", data={"code":code}).status_code == 401


def test_recovery_codes_are_hashed(client, app):
    register(client)
    login(client)
    client.get("/security/2fa/enable")
    secret = secret_for(app)
    response = client.post("/security/2fa/enable", data={"code":pyotp.TOTP(secret).now()})
    codes = re.findall(rb"<code>([^<]+)</code>", response.data)
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert len(codes) == len(user.recovery_codes_hash) == 8
        assert all(code.decode().encode() not in digest.encode() for code, digest in zip(codes, user.recovery_codes_hash))

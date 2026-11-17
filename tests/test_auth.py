import bcrypt
from app.extensions import db
from app.models import User
from .conftest import login, register


def test_registration_and_bcrypt_hash(client, app):
    response = register(client)
    assert b"Your account is ready" in response.data
    with app.app_context():
        user = db.session.scalar(db.select(User))
        assert user.password_hash != b"Passw0rd!"
        assert bcrypt.checkpw(b"Passw0rd!", user.password_hash)


def test_duplicate_email_rejected(client):
    register(client)
    response = register(client, username="another", email="USER@example.com")
    assert b"email is already registered" in response.data


def test_duplicate_username_rejected(client):
    register(client)
    response = register(client, username="SAMPLE_USER", email="other@example.com")
    assert b"username is already in use" in response.data


def test_weak_password_rejected(client):
    response = register(client, password="password")
    assert b"Password must be" in response.data


def test_successful_login_by_username_and_email(client):
    register(client)
    assert b"Welcome, Sample" in login(client).data
    client.post("/logout")
    assert b"Welcome, Sample" in login(client, identity="USER@example.com").data


def test_bad_password_has_generic_error(client):
    register(client)
    response = client.post("/login", data={"identity":"sample_user", "password":"wrong"})
    assert response.status_code == 401
    assert b"Invalid username/email or password" in response.data


def test_invalid_input_rejected(client):
    response = client.post("/register", data={"full_name":"x", "username":"?", "email":"bad", "password":"x", "confirm_password":"y"})
    assert response.status_code == 200
    assert b"valid email" in response.data
    assert b"Passwords do not match" in response.data


def test_inactive_account_rejected(client, app):
    register(client)
    with app.app_context():
        user = db.session.scalar(db.select(User))
        user.is_active = False
        db.session.commit()
    response = client.post("/login", data={"identity":"sample_user", "password":"Passw0rd!"})
    assert response.status_code == 401

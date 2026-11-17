import pytest
from app import create_app
from app.extensions import db


@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False,
                      "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
                      "RATELIMIT_ENABLED": True})
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username="sample_user", email="user@example.com", password="Passw0rd!"):
    return client.post("/register", data={"full_name":"Sample User", "username":username,
                       "email":email, "password":password, "confirm_password":password}, follow_redirects=True)


def login(client, identity="sample_user", password="Passw0rd!"):
    return client.post("/login", data={"identity":identity, "password":password}, follow_redirects=True)

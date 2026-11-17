import pytest

from app import create_app
from app.extensions import db


def test_production_requires_existing_database_file(tmp_path):
    database_path = tmp_path / "missing.db"
    with pytest.raises(RuntimeError, match="Production database file is missing"):
        create_app({
            "TESTING": True,
            "APP_ENV": "production",
            "DATABASE_PATH": str(database_path),
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        })


def test_production_forces_secure_cookies(tmp_path):
    database_path = tmp_path / "production.db"
    database_path.touch()
    app = create_app({
        "TESTING": True,
        "APP_ENV": "production",
        "DATABASE_PATH": str(database_path),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
    })
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["TRUST_PROXY"] is True
    assert app.config["PREFERRED_URL_SCHEME"] == "https"
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_database_bootstrap_requires_maintenance_mode(tmp_path):
    database_path = tmp_path / "bootstrap.db"
    with pytest.raises(RuntimeError, match="only permitted while MAINTENANCE_MODE"):
        create_app({
            "TESTING": True,
            "APP_ENV": "production",
            "DATABASE_PATH": str(database_path),
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "ALLOW_DATABASE_INIT": True,
        })

    app = create_app({
        "TESTING": True,
        "APP_ENV": "production",
        "DATABASE_PATH": str(database_path),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        "ALLOW_DATABASE_INIT": True,
        "MAINTENANCE_MODE": True,
    })
    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/login").status_code == 503
    with app.app_context():
        db.session.remove()
        db.drop_all()

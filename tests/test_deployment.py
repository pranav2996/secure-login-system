import pytest

from app import create_app


def test_production_requires_database_url():
    with pytest.raises(RuntimeError, match="Set DATABASE_URL"):
        create_app({
            "APP_ENV": "production",
            "DATABASE_URL": "",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })


def test_production_rejects_sqlite_database_url():
    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        create_app({
            "APP_ENV": "production",
            "DATABASE_URL": "sqlite:///should_not_be_created.db",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///should_not_be_created.db",
        })


def test_production_forces_secure_cookies_on_test_database(tmp_path):
    database_path = tmp_path / "production-config-test.db"
    app = create_app({
        "TESTING": True,
        "APP_ENV": "production",
        "DATABASE_URL": "",
        "DATABASE_PATH": str(database_path),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
    })
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["TRUST_PROXY"] is True
    assert app.config["PREFERRED_URL_SCHEME"] == "https"
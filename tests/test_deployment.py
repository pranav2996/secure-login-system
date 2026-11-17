import os
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app import create_app
from app.extensions import db
from app.models import User
from config import normalize_database_url


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


def test_production_initializes_and_reuses_a_fresh_local_postgresql_schema():
    test_url = os.environ.get("TEST_POSTGRESQL_URL")
    if not test_url:
        pytest.skip("Set TEST_POSTGRESQL_URL to a disposable local PostgreSQL database to run this integration test.")
    parsed = make_url(test_url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("Production schema integration tests are restricted to local PostgreSQL; remote/Neon URLs are refused.")
    pytest.importorskip("psycopg")

    normalized_url = normalize_database_url(test_url, require_ssl=True)
    schema = "app_init_test_" + uuid.uuid4().hex
    admin_engine = create_engine(normalized_url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    app_instances = []
    try:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        app_config = {
            "APP_ENV": "production",
            "DATABASE_URL": test_url,
            "SQLALCHEMY_DATABASE_URI": normalized_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {
                "poolclass": NullPool,
                "connect_args": {"connect_timeout": 5, "options": f"-csearch_path={schema}"},
            },
            "SECRET_KEY": "test-only-production-secret",
            "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }

        first_app = create_app(app_config)
        app_instances.append(first_app)
        with first_app.app_context():
            assert inspect(db.engine).has_table("user")
            created_user = User(
                full_name="Schema Test",
                username="schema_" + uuid.uuid4().hex[:12],
                email=uuid.uuid4().hex + "@example.test",
                password_hash=b"test-hash",
            )
            db.session.add(created_user)
            db.session.commit()
            saved_id = created_user.id

        second_app = create_app(app_config)
        app_instances.append(second_app)
        with second_app.app_context():
            assert inspect(db.engine).has_table("user")
            saved = db.session.execute(select(User).where(User.id == saved_id)).scalar_one()
            assert saved.username.startswith("schema_")
    finally:
        for app_instance in app_instances:
            with app_instance.app_context():
                db.session.remove()
                db.engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin_engine.dispose()

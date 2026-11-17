import os
import uuid
from datetime import datetime, timezone

import bcrypt
import pytest
from sqlalchemy import create_engine, inspect, insert, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.models import User
from config import normalize_database_url
from migrate_sqlite_to_postgres import MigrationError, migrate


def _sample_record(user_id=41, username="migrate_user", email="migrate@example.test"):
    return {
        "id": user_id,
        "full_name": "Migration Test",
        "username": username,
        "email": email,
        "password_hash": bcrypt.hashpw(b"not-a-real-account-password", bcrypt.gensalt(rounds=4)),
        "is_active": True,
        "is_2fa_enabled": True,
        "totp_secret": b"encrypted-totp-bytes",
        "pending_totp_secret": None,
        "recovery_codes_hash": [bcrypt.hashpw(b"TEST-RECOVERY-CODE", bcrypt.gensalt(rounds=4)).decode()],
        "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        "updated_at": datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
        "last_login": datetime(2025, 3, 4, 5, 6, 7, tzinfo=timezone.utc),
    }


def _make_source(path, records=None):
    engine = create_engine(f"sqlite:///{path}")
    User.metadata.create_all(engine)
    if records:
        with engine.begin() as connection:
            connection.execute(insert(User.__table__), records)
    engine.dispose()


def test_migration_copies_hashes_ids_encrypted_totp_recovery_and_timestamps(tmp_path):
    source_path = tmp_path / "temporary-source.db"
    destination_path = tmp_path / "temporary-destination.db"
    source_record = _sample_record()
    _make_source(source_path, [source_record])
    destination_engine = create_engine(f"sqlite:///{destination_path}")

    report = migrate(source_path, destination_engine, apply=True, confirmed=True)
    assert report.source_records == 1
    assert report.inserted == 1
    assert report.already_present == 0
    assert report.created_user_table is True
    with destination_engine.connect() as connection:
        copied = connection.execute(select(User.__table__)).mappings().one()
    assert copied["id"] == source_record["id"]
    assert bytes(copied["password_hash"]) == source_record["password_hash"]
    assert bytes(copied["totp_secret"]) == source_record["totp_secret"]
    assert copied["pending_totp_secret"] is None
    assert copied["recovery_codes_hash"] == source_record["recovery_codes_hash"]
    assert copied["is_2fa_enabled"] is True
    assert copied["created_at"].replace(tzinfo=timezone.utc) == source_record["created_at"]
    assert copied["updated_at"].replace(tzinfo=timezone.utc) == source_record["updated_at"]
    assert copied["last_login"].replace(tzinfo=timezone.utc) == source_record["last_login"]
    destination_engine.dispose()


def test_migration_dry_run_does_not_create_destination_tables(tmp_path):
    source_path = tmp_path / "temporary-source.db"
    destination_path = tmp_path / "temporary-destination.db"
    _make_source(source_path, [_sample_record()])
    destination_engine = create_engine(f"sqlite:///{destination_path}")

    report = migrate(source_path, destination_engine)
    assert report.inserted == 1
    assert report.created_user_table is False
    assert inspect(destination_engine).get_table_names() == []
    destination_engine.dispose()


def test_migration_is_idempotent_and_never_overwrites_conflicting_rows(tmp_path):
    source_path = tmp_path / "temporary-source.db"
    destination_path = tmp_path / "temporary-destination.db"
    source_record = _sample_record()
    _make_source(source_path, [source_record])
    destination_engine = create_engine(f"sqlite:///{destination_path}")

    first = migrate(source_path, destination_engine, apply=True, confirmed=True)
    second = migrate(source_path, destination_engine, apply=True, confirmed=True)
    assert first.inserted == 1
    assert second.inserted == 0
    assert second.already_present == 1
    with destination_engine.begin() as connection:
        connection.execute(update(User.__table__).where(User.id == source_record["id"]).values(email="different@example.test"))
    with pytest.raises(MigrationError, match="refusing to overwrite"):
        migrate(source_path, destination_engine, apply=True, confirmed=True)
    with destination_engine.connect() as connection:
        email = connection.execute(select(User.email).where(User.id == source_record["id"])).scalar_one()
    assert email == "different@example.test"
    destination_engine.dispose()


def test_migration_refuses_case_insensitive_duplicate_source_accounts(tmp_path):
    source_path = tmp_path / "temporary-source.db"
    destination_path = tmp_path / "temporary-destination.db"
    first = _sample_record(1, "Same_User", "one@example.test")
    second = _sample_record(2, "same_user", "two@example.test")
    _make_source(source_path, [first, second])
    destination_engine = create_engine(f"sqlite:///{destination_path}")

    with pytest.raises(MigrationError, match="Duplicate username"):
        migrate(source_path, destination_engine)
    assert inspect(destination_engine).get_table_names() == []
    destination_engine.dispose()


def test_migration_requires_explicit_confirmation_for_writes(tmp_path):
    source_path = tmp_path / "temporary-source.db"
    destination_path = tmp_path / "temporary-destination.db"
    _make_source(source_path, [_sample_record()])
    destination_engine = create_engine(f"sqlite:///{destination_path}")

    with pytest.raises(MigrationError, match="explicit confirmation"):
        migrate(source_path, destination_engine, apply=True)
    assert inspect(destination_engine).get_table_names() == []
    destination_engine.dispose()


def test_postgresql_migration_in_a_temporary_local_schema_when_available(tmp_path):
    test_url = os.environ.get("TEST_POSTGRESQL_URL")
    if not test_url:
        pytest.skip("Set TEST_POSTGRESQL_URL to a disposable local PostgreSQL database to run this integration test.")
    parsed = make_url(test_url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.skip("PostgreSQL integration tests are restricted to local disposable databases; remote/Neon URLs are refused.")
    pytest.importorskip("psycopg")

    schema = "migration_test_" + uuid.uuid4().hex
    normalized = normalize_database_url(test_url, require_ssl=True)
    admin_engine = create_engine(normalized, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        target_engine = create_engine(
            normalized,
            poolclass=NullPool,
            connect_args={"connect_timeout": 5, "options": f"-csearch_path={schema}"},
        )
        source_path = tmp_path / "temporary-source.db"
        _make_source(source_path, [_sample_record()])
        try:
            report = migrate(source_path, target_engine, apply=True, confirmed=True)
            assert report.inserted == 1
            rerun = migrate(source_path, target_engine, apply=True, confirmed=True)
            assert rerun.inserted == 0
            assert rerun.already_present == 1
        finally:
            target_engine.dispose()
    finally:
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin_engine.dispose()

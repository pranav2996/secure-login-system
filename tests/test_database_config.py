from sqlalchemy.engine import make_url

from config import database_settings, normalize_database_url


def test_sqlite_local_database_remains_supported():
    uri, options = database_settings("", database_path="")
    assert uri == "sqlite:///secure_login.db"
    assert options["connect_args"]["timeout"] == 30


def test_sqlite_database_path_stays_sqlite():
    uri, options = database_settings("sqlite:///local-test.db")
    assert make_url(uri).get_backend_name() == "sqlite"
    assert options["pool_pre_ping"] is True


def test_postgres_urls_normalize_to_psycopg_and_require_tls():
    uri = normalize_database_url(
        "postgres://test-role:test-password@example-pooler.neon.tech/app?sslmode=disable&channel_binding=require",
        require_ssl=True,
    )
    parsed = make_url(uri)
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.query["sslmode"] == "require"
    assert parsed.query["channel_binding"] == "require"


def test_strict_postgres_tls_mode_is_preserved():
    uri = normalize_database_url(
        "postgresql://test-role:test-password@localhost/app?sslmode=verify-full",
        require_ssl=True,
    )
    assert make_url(uri).query["sslmode"] == "verify-full"


def test_neon_pool_uses_small_recycled_health_checked_pool():
    _uri, options = database_settings(
        "postgresql://test-role:test-password@example-pooler.neon.tech/app",
        production=True,
    )
    assert options["pool_size"] == 1
    assert options["max_overflow"] == 0
    assert options["pool_pre_ping"] is True
    assert options["pool_recycle"] == 240
    assert options["connect_args"]["connect_timeout"] == 30
    assert options["connect_args"]["prepare_threshold"] is None

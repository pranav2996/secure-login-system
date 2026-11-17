"""Safely copy the current application's SQLite user table to PostgreSQL.

The command defaults to a read-only dry run. A write requires both --apply and
--confirm. The original SQLite file is opened with mode=ro and is never changed.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, func, inspect, insert, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from config import normalize_database_url
from app.models import User


class MigrationError(RuntimeError):
    """Raised when source or destination data is not safe to migrate."""


@dataclass(frozen=True)
class MigrationReport:
    source_records: int
    destination_records_before: int
    inserted: int
    already_present: int
    destination_records_after: int
    created_user_table: bool


REQUIRED_COLUMNS = tuple(User.__table__.columns.keys())
TABLE_NAME = User.__tablename__


def _utc_datetime(value, *, field_name):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise MigrationError(f"Invalid timestamp in source column {field_name}.") from exc
    if not isinstance(value, datetime):
        raise MigrationError(f"Unexpected value in source timestamp column {field_name}.")
    if value.tzinfo is None:
        # The application writes UTC-aware timestamps; SQLite drops the zone.
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _read_sqlite_source(source_path):
    path = Path(source_path).expanduser().resolve()
    if not path.is_file():
        raise MigrationError("SQLite source file does not exist.")

    uri = path.as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=30)
    except sqlite3.Error as exc:
        raise MigrationError("Could not open SQLite source in read-only mode.") from exc
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables != {TABLE_NAME}:
            raise MigrationError("SQLite contains unknown or missing application tables; review its schema before migration.")

        info = list(connection.execute(f'PRAGMA table_info("{TABLE_NAME}")'))
        column_names = tuple(row["name"] for row in info)
        if set(column_names) != set(REQUIRED_COLUMNS):
            raise MigrationError("SQLite user-table columns do not match the current application model.")
        primary_keys = [row["name"] for row in info if row["pk"]]
        if primary_keys != ["id"]:
            raise MigrationError("SQLite user-table primary key does not match the application model.")

        unique_sets = set()
        for index in connection.execute(f'PRAGMA index_list("{TABLE_NAME}")'):
            if index["unique"]:
                index_name = index["name"].replace('"', '""')
                columns = tuple(
                    row["name"]
                    for row in connection.execute(f'PRAGMA index_info("{index_name}")')
                )
                unique_sets.add(columns)
        if not {("username",), ("email",)}.issubset(unique_sets):
            raise MigrationError("SQLite user-table uniqueness constraints are missing or incompatible.")

        quoted = ", ".join(f'"{name}"' for name in REQUIRED_COLUMNS)
        rows = [dict(row) for row in connection.execute(f'SELECT {quoted} FROM "{TABLE_NAME}" ORDER BY id')]
    except sqlite3.Error as exc:
        raise MigrationError("Could not inspect or read the SQLite source schema.") from exc
    finally:
        connection.close()

    for row in rows:
        try:
            row["id"] = int(row["id"])
        except (TypeError, ValueError) as exc:
            raise MigrationError("SQLite contains an invalid user primary key.") from exc
        row["is_active"] = bool(row["is_active"])
        row["is_2fa_enabled"] = bool(row["is_2fa_enabled"])
        for field in ("password_hash", "totp_secret", "pending_totp_secret"):
            if row[field] is not None:
                try:
                    row[field] = bytes(row[field])
                except (TypeError, ValueError) as exc:
                    raise MigrationError(f"SQLite contains invalid binary data in {field}.") from exc
        recovery = row["recovery_codes_hash"]
        if isinstance(recovery, str):
            try:
                recovery = json.loads(recovery)
            except json.JSONDecodeError as exc:
                raise MigrationError("SQLite recovery-code data is not valid JSON.") from exc
        if not isinstance(recovery, list) or any(not isinstance(item, str) for item in recovery):
            raise MigrationError("SQLite recovery-code data does not match the application model.")
        row["recovery_codes_hash"] = recovery
        for field in ("created_at", "updated_at", "last_login"):
            if field != "last_login" and row[field] is None:
                raise MigrationError(f"SQLite is missing required timestamp {field}.")
            row[field] = _utc_datetime(row[field], field_name=field)

    _validate_unique_records(rows, location="SQLite source")
    return rows


def _validate_unique_records(rows, *, location):
    ids = set()
    usernames = set()
    emails = set()
    for row in rows:
        if row["id"] in ids:
            raise MigrationError(f"Duplicate primary key detected in {location}.")
        ids.add(row["id"])
        if not isinstance(row.get("username"), str) or not isinstance(row.get("email"), str):
            raise MigrationError(f"Invalid account identity data detected in {location}.")
        username = row["username"].casefold()
        email = row["email"].casefold()
        if username in usernames:
            raise MigrationError(f"Duplicate username detected in {location} (case-insensitive check).")
        if email in emails:
            raise MigrationError(f"Duplicate email detected in {location} (case-insensitive check).")
        usernames.add(username)
        emails.add(email)


def _normalize_for_compare(row):
    result = dict(row)
    for key in ("created_at", "updated_at", "last_login"):
        result[key] = _utc_datetime(result.get(key), field_name=key)
    for key in ("password_hash", "totp_secret", "pending_totp_secret"):
        if result.get(key) is not None:
            result[key] = bytes(result[key])
    recovery = result.get("recovery_codes_hash")
    if isinstance(recovery, str):
        recovery = json.loads(recovery)
    result["recovery_codes_hash"] = recovery
    result["is_active"] = bool(result["is_active"])
    result["is_2fa_enabled"] = bool(result["is_2fa_enabled"])
    return result


def _schema_and_records(connection, engine):
    inspector = inspect(connection)
    if engine.dialect.name == "postgresql":
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
    else:
        schema = None
    tables = set(inspector.get_table_names(schema=schema))
    if TABLE_NAME not in tables:
        if tables:
            raise MigrationError("Destination contains tables outside this application's known schema; refusing to modify it.")
        return schema, [], False
    if tables != {TABLE_NAME}:
        raise MigrationError("Destination contains unknown application tables; review its schema before migration.")

    columns = inspector.get_columns(TABLE_NAME, schema=schema)
    by_name = {column["name"]: column for column in columns}
    if set(by_name) != set(REQUIRED_COLUMNS):
        raise MigrationError("PostgreSQL user-table columns do not match the current application model.")
    if engine.dialect.name == "postgresql":
        for column in User.__table__.columns:
            expected_type = column.type.compile(dialect=engine.dialect).lower()
            actual_type = by_name[column.name]["type"].compile(dialect=engine.dialect).lower()
            if actual_type != expected_type:
                raise MigrationError("PostgreSQL user-table column types do not match the current application model.")
    primary_key = inspector.get_pk_constraint(TABLE_NAME, schema=schema).get("constrained_columns") or []
    if primary_key != ["id"]:
        raise MigrationError("Destination user-table primary key does not match the application model.")

    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(TABLE_NAME, schema=schema)
    }
    unique_sets.update(
        tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(TABLE_NAME, schema=schema)
        if item.get("unique")
    )
    if not {("username",), ("email",)}.issubset(unique_sets):
        raise MigrationError("Destination user-table uniqueness constraints are missing or incompatible.")

    records = [dict(row) for row in connection.execute(select(User.__table__)).mappings()]
    _validate_unique_records(records, location="PostgreSQL destination")
    return schema, records, True


def migrate(source_path, destination_engine: Engine, *, apply=False, confirmed=False):
    """Plan or execute a single-table, append-only migration.

    SQLite destinations are supported only for isolated automated tests. The CLI
    separately requires a PostgreSQL DATABASE_URL and an explicit confirmation.
    """
    if apply and not confirmed:
        raise MigrationError("A real migration requires explicit confirmation.")
    if not apply and confirmed:
        raise MigrationError("Confirmation is only valid together with apply mode.")

    source_rows = _read_sqlite_source(source_path)
    table_created = False
    table = User.__table__

    with destination_engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema, destination_rows, table_exists = _schema_and_records(connection, destination_engine)
            if not table_exists and apply:
                table = User.__table__.to_metadata(MetaData(), schema=schema)
                table.create(connection, checkfirst=False)
                table_created = True
                schema, destination_rows, table_exists = _schema_and_records(connection, destination_engine)

            by_id = {row["id"]: _normalize_for_compare(row) for row in destination_rows}
            by_username = {row["username"].casefold(): row["id"] for row in destination_rows}
            by_email = {row["email"].casefold(): row["id"] for row in destination_rows}
            to_insert = []
            already_present = 0
            for source_row in source_rows:
                source_cmp = _normalize_for_compare(source_row)
                existing = by_id.get(source_row["id"])
                if existing is not None:
                    if existing != source_cmp:
                        raise MigrationError("Destination has a conflicting row with a source primary key; refusing to overwrite it.")
                    already_present += 1
                    continue
                if source_row["username"].casefold() in by_username:
                    raise MigrationError("Destination already contains a source username under a different primary key.")
                if source_row["email"].casefold() in by_email:
                    raise MigrationError("Destination already contains a source email under a different primary key.")
                to_insert.append(source_row)

            before_count = len(destination_rows)
            if apply and to_insert:
                connection.execute(insert(table), to_insert)

            if apply:
                verify_schema = table if table_created else User.__table__
                migrated_rows = {
                    row["id"]: _normalize_for_compare(row)
                    for row in connection.execute(select(verify_schema)).mappings()
                }
                for source_row in source_rows:
                    if migrated_rows.get(source_row["id"]) != _normalize_for_compare(source_row):
                        raise MigrationError("Post-migration validation did not match the source records.")

                if destination_engine.dialect.name == "postgresql":
                    qualified_table = f"{schema}.{TABLE_NAME}" if schema else TABLE_NAME
                    max_id = connection.execute(select(func.max(table.c.id))).scalar_one()
                    sequence = connection.execute(
                        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                        {"table_name": qualified_table},
                    ).scalar_one()
                    if sequence:
                        connection.execute(
                            text("SELECT setval(CAST(:sequence_name AS regclass), :value, :is_called)"),
                            {"sequence_name": sequence, "value": max_id or 1, "is_called": max_id is not None},
                        )
                transaction.commit()
                after_count = connection.execute(select(func.count()).select_from(table)).scalar_one()
            else:
                transaction.rollback()
                after_count = before_count + len(to_insert)

            return MigrationReport(
                source_records=len(source_rows),
                destination_records_before=before_count,
                inserted=len(to_insert),
                already_present=already_present,
                destination_records_after=after_count,
                created_user_table=table_created,
            )
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dry-run or explicitly migrate the application SQLite users to PostgreSQL.")
    parser.add_argument("--source", required=True, help="Path to the SQLite database to read in read-only mode.")
    parser.add_argument("--apply", action="store_true", help="Write to PostgreSQL. Requires --confirm.")
    parser.add_argument("--confirm", action="store_true", help="Explicitly confirm an append-only PostgreSQL migration.")
    args = parser.parse_args(argv)

    if args.apply != args.confirm:
        parser.error("a real migration requires both --apply and --confirm; omit both for a dry run")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must be set in the environment; it is never read from .env by this utility")
    try:
        normalized_url = normalize_database_url(database_url, require_ssl=True)
        url = make_url(normalized_url)
        if url.get_backend_name() != "postgresql":
            parser.error("DATABASE_URL must point to PostgreSQL")
        from sqlalchemy import create_engine

        engine = create_engine(
            normalized_url,
            poolclass=NullPool,
            connect_args={"connect_timeout": 30, "prepare_threshold": None},
        )
        try:
            report = migrate(args.source, engine, apply=args.apply, confirmed=args.confirm)
        finally:
            engine.dispose()
    except MigrationError as exc:
        print(f"Migration stopped safely: {exc}", file=sys.stderr)
        return 2
    except (SQLAlchemyError, sqlite3.Error, OSError, ValueError, TypeError) as exc:
        # Avoid echoing driver exception text, which can contain connection details.
        print(f"Migration failed safely ({type(exc).__name__}); details were withheld to protect connection data.", file=sys.stderr)
        return 2

    mode = "APPLIED" if args.apply else "DRY RUN — no changes made"
    print(
        f"{mode}: source={report.source_records}, "
        f"destination_before={report.destination_records_before}, "
        f"inserted={report.inserted}, already_present={report.already_present}, "
        f"destination_after={report.destination_records_after}, "
        f"created_user_table={report.created_user_table}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Narrow psycopg adapter for KEDR's existing parameterized persistence SQL.

This is deliberately not a general SQL dialect translator. The few SQLite-only
forms below are the forms used by KEDR. PostgreSQL schema is explicit and lives
in postgres_migrations, independently of the unchanged local SQLite migrations.
Connection strings and database exceptions containing values are never logged.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import re
import sqlite3


class CompatibleRow(Mapping):
    """A result row with sqlite3.Row's name and integer indexing contracts."""

    def __init__(self, names, values):
        self._names = tuple(names)
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        try:
            return self._values[self._names.index(key)]
        except ValueError:
            raise KeyError(key) from None

    def __iter__(self):
        return iter(self._names)

    def __len__(self):
        return len(self._names)


def compatible_row(cursor):
    names = [item.name for item in cursor.description] if cursor.description else []
    return lambda values: CompatibleRow(names, values)


def translate_sql(sql: str, *, parameterized: bool = True) -> str:
    """Translate only application dialect forms; never interpolate parameters."""
    sql = re.sub(
        r"\b([a-z_][a-z_0-9.]*)\s*=\s*\?\s+COLLATE\s+NOCASE\b",
        r"kedr_nocase(\1)=kedr_nocase(?)", sql, flags=re.IGNORECASE,
    )
    # SQLite's scalar MAX with two arguments is PostgreSQL GREATEST. Leave
    # aggregate MAX(number) and COALESCE(MAX(number),...) untouched.
    sql = re.sub(r"\bMAX\((accounted_tokens|accounted_usd)\s*,\s*\?\)", r"GREATEST(\1,?)", sql, flags=re.IGNORECASE)
    if not parameterized:
        return sql
    # psycopg requires literal percent signs escaped when parameters are passed.
    # Preserve question marks inside quoted SQL text and comments.
    out = []
    index = 0
    quote = None
    while index < len(sql):
        char = sql[index]
        if quote:
            out.append("%%" if char == "%" else char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    out.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            out.append(char)
        elif sql[index:index + 2] in ("--", "/*"):
            end = sql.find("\n", index + 2) if char == "-" else sql.find("*/", index + 2)
            if end < 0:
                end = len(sql)
            elif char == "/":
                end += 2
            out.append(sql[index:end].replace("%", "%%"))
            index = end
            continue
        else:
            out.append("%s" if char == "?" else "%%" if char == "%" else char)
        index += 1
    return "".join(out)


class EmptyCursor:
    rowcount = -1

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


@contextmanager
def connect_postgres(database_url):
    try:
        import psycopg
    except ImportError:
        raise RuntimeError("PostgreSQL requires the pinned psycopg dependency; install requirements.txt.") from None
    try:
        raw = psycopg.connect(database_url, connect_timeout=10, row_factory=compatible_row)
        raw.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
    except psycopg.Error:
        # libpq diagnostics may contain host names, user names or DSN fragments.
        raise RuntimeError("Unable to connect to the configured PostgreSQL database.") from None
    with raw:
        yield raw


class PostgresConnection:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, parameters=None):
        if sql.strip().rstrip(";").upper() == "BEGIN IMMEDIATE":
            # Database.connection already acquired the transaction advisory lock.
            return EmptyCursor()
        import psycopg
        try:
            # SQLite integrity errors abort a statement, not the surrounding
            # transaction. A savepoint retains that contract for callers which
            # deliberately catch sqlite3.IntegrityError inside a context.
            with self.raw.transaction():
                return self.raw.execute(translate_sql(sql, parameterized=parameters is not None), parameters)
        except psycopg.IntegrityError as exc:
            immutable = "immutable" in (exc.diag.message_primary or "").lower()
            message = "immutable database record" if immutable else {
                "23505": "unique constraint failed",
                "23503": "foreign key constraint failed",
                "23502": "not null constraint failed",
                "23514": "check constraint failed",
            }.get(exc.sqlstate, "database constraint failed")
            raise sqlite3.IntegrityError(message) from None

    def executescript(self, sql):
        # Migration bodies contain explicit PostgreSQL functions and triggers;
        # psycopg's unparameterized simple-query path handles the complete script.
        return self.raw.execute(sql, prepare=False)

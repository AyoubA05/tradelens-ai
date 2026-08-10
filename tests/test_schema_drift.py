"""The schema-drift comparator must catch the drift we already know about.

A comparison tool that reports "no differences" is worthless unless it has been
shown to fail on a real difference. The specific case it has to catch is the
one confirmed in production on 2026-08-10: the `users.email` column exists, but
the unique index Alembic revision r8s9t0u1v2w3 creates does not.

That drift arose because `init_db._reconcile_columns` adds missing *columns*
via ALTER TABLE and never creates indexes, so any index introduced after a
table was first built by create_all is silently absent.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from scripts.schema_drift import compare


def _build(url: str, statements: list) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


_REFERENCE = [
    "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR NOT NULL, "
    "email VARCHAR)",
    "CREATE UNIQUE INDEX ix_users_email ON users (email)",
    "CREATE INDEX ix_users_username ON users (username)",
]


def test_identical_schemas_report_no_drift(tmp_path):
    ref = f"sqlite:///{tmp_path / 'ref.db'}"
    tgt = f"sqlite:///{tmp_path / 'tgt.db'}"
    _build(ref, _REFERENCE)
    _build(tgt, _REFERENCE)

    benign, drift = compare(ref, tgt)

    assert drift == [], f"identical schemas must not report drift: {drift}"


def test_the_missing_email_unique_index_is_detected(tmp_path):
    """The exact production drift."""
    ref = f"sqlite:///{tmp_path / 'ref.db'}"
    tgt = f"sqlite:///{tmp_path / 'tgt.db'}"
    _build(ref, _REFERENCE)
    _build(
        tgt,
        [
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR NOT NULL, "
            "email VARCHAR)",
            "CREATE INDEX ix_users_username ON users (username)",
        ],
    )

    _benign, drift = compare(ref, tgt)

    assert any(
        "ix_users_email" in line for line in drift
    ), f"the missing unique index must be reported as drift, got: {drift}"


def test_a_missing_table_is_detected(tmp_path):
    ref = f"sqlite:///{tmp_path / 'ref.db'}"
    tgt = f"sqlite:///{tmp_path / 'tgt.db'}"
    _build(ref, _REFERENCE + ["CREATE TABLE strategies (id INTEGER PRIMARY KEY)"])
    _build(tgt, _REFERENCE)

    _benign, drift = compare(ref, tgt)

    assert any("strategies" in line for line in drift)


def test_a_nullability_difference_is_detected(tmp_path):
    """Nullability drift is how a NOT NULL column quietly becomes optional.

    init_db._reconcile_columns skips columns that are NOT NULL without a server
    default, so this is a live possibility on this database, not a hypothetical.
    """
    ref = f"sqlite:///{tmp_path / 'ref.db'}"
    tgt = f"sqlite:///{tmp_path / 'tgt.db'}"
    _build(ref, ["CREATE TABLE t (id INTEGER PRIMARY KEY, flag INTEGER NOT NULL)"])
    _build(tgt, ["CREATE TABLE t (id INTEGER PRIMARY KEY, flag INTEGER)"])

    _benign, drift = compare(ref, tgt)

    assert any("NULLABLE" in line for line in drift)


def test_alembic_version_is_not_reported_as_drift(tmp_path):
    """Its absence is the reason for the exercise, not a finding within it."""
    ref = f"sqlite:///{tmp_path / 'ref.db'}"
    tgt = f"sqlite:///{tmp_path / 'tgt.db'}"
    _build(ref, _REFERENCE + ["CREATE TABLE alembic_version (version_num VARCHAR)"])
    _build(tgt, _REFERENCE)

    _benign, drift = compare(ref, tgt)

    assert not any("alembic_version" in line for line in drift)

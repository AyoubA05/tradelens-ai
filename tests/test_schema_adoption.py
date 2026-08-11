"""Contract for canonical schema convergence.

The riskiest part is not the DDL, it is the *ordering* of the username
convergence: the target index has to take a name the old index already holds,
while the uniqueness invariant stays enforced throughout. Those orderings are
unit-tested as a pure function so they can be reasoned about without a database.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from src.tradelens.db.models import Base
from src.tradelens.db.schema_adoption import username_convergence_statements

_REPO = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Username convergence ordering
# ---------------------------------------------------------------------------


def test_tracked_lineage_never_leaves_username_uniqueness_unenforced():
    """The r8 shape: a unique constraint plus a separate non-unique index.

    Uniqueness must be held by something after every statement. The only
    ordering that achieves it without a temporary name drops the non-unique
    index first — freeing the name while the constraint still protects the
    column — then creates the unique index, then drops the constraint.
    """
    statements = username_convergence_statements(
        uq_constraint_present=True, ix_present=True, ix_is_unique=False
    )

    assert statements == [
        "DROP INDEX ix_users_username",
        "CREATE UNIQUE INDEX ix_users_username ON users USING btree (username)",
        "ALTER TABLE users DROP CONSTRAINT uq_users_username",
    ]

    # Walk the sequence and assert the invariant holds at every point.
    has_constraint, has_unique_index = True, False
    for statement in statements:
        if statement.startswith("DROP INDEX"):
            pass  # dropping the NON-unique index removes no guarantee
        elif statement.startswith("CREATE UNIQUE INDEX"):
            has_unique_index = True
        elif "DROP CONSTRAINT" in statement:
            has_constraint = False
        assert (
            has_constraint or has_unique_index
        ), f"uniqueness unenforced after: {statement}"


def test_the_constraint_is_dropped_only_after_the_unique_index_exists():
    statements = username_convergence_statements(
        uq_constraint_present=True, ix_present=True, ix_is_unique=False
    )
    create = next(
        i for i, s in enumerate(statements) if s.startswith("CREATE UNIQUE INDEX")
    )
    drop = next(i for i, s in enumerate(statements) if "DROP CONSTRAINT" in s)
    assert create < drop


def test_the_name_is_freed_before_it_is_reused():
    """Creating before dropping would collide on ix_users_username."""
    statements = username_convergence_statements(
        uq_constraint_present=True, ix_present=True, ix_is_unique=False
    )
    drop_index = statements.index("DROP INDEX ix_users_username")
    create = next(
        i for i, s in enumerate(statements) if s.startswith("CREATE UNIQUE INDEX")
    )
    assert drop_index < create


def test_the_untracked_lineage_is_already_canonical():
    """Production already has exactly one unique index and no constraint."""
    assert (
        username_convergence_statements(
            uq_constraint_present=False, ix_present=True, ix_is_unique=True
        )
        == []
    )


def test_a_database_with_no_username_index_at_all_gets_one():
    statements = username_convergence_statements(
        uq_constraint_present=False, ix_present=False, ix_is_unique=False
    )
    assert statements == [
        "CREATE UNIQUE INDEX ix_users_username ON users USING btree (username)"
    ]


# ---------------------------------------------------------------------------
# Server defaults — Decision 3
# ---------------------------------------------------------------------------


def _fresh(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'defaults.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_raw_insert_omitting_is_active_receives_the_database_default(tmp_path):
    """The ORM always supplies this; a raw INSERT is what the default is for.

    Before the server_default was declared, this statement failed outright:
    the column is NOT NULL with only a Python-side default, which the database
    never sees.
    """
    engine = _fresh(tmp_path)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (username, password_hash) VALUES ('raw', 'h')")
        )
        assert (
            conn.execute(
                text("SELECT is_active FROM users WHERE username='raw'")
            ).scalar()
            == 1
        )


def test_raw_insert_omitting_is_sample_receives_the_database_default(tmp_path):
    engine = _fresh(tmp_path)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO trades (asset) VALUES ('EURUSD')"))
        assert (
            conn.execute(
                text("SELECT is_sample FROM trades WHERE asset='EURUSD'")
            ).scalar()
            == 0
        )


def test_python_and_server_defaults_do_not_disagree(tmp_path):
    """Two defaults on one column is a bug unless they agree."""
    for column, table in (("is_active", "users"), ("is_sample", "trades")):
        col = Base.metadata.tables[table].c[column]
        python_default = col.default.arg
        server_default = str(col.server_default.arg)
        assert str(python_default) == server_default.strip("'"), (
            f"{table}.{column}: python default {python_default!r} disagrees with "
            f"server default {server_default!r}"
        )


# ---------------------------------------------------------------------------
# Redundant primary-key indexes — Decision 1 and 2
# ---------------------------------------------------------------------------


def test_the_four_adopted_tables_no_longer_index_their_primary_key(tmp_path):
    """A second btree on the PK column answers nothing users_pkey cannot."""
    engine = _fresh(tmp_path)
    inspector = inspect(engine)
    for table in ("users", "corrections", "ai_usage_log", "performance_metrics"):
        names = {i["name"] for i in inspector.get_indexes(table)}
        assert (
            f"ix_{table}_id" not in names
        ), f"ix_{table}_id is redundant with the primary key index"


def test_the_six_deferred_tables_still_index_their_primary_key(tmp_path):
    """Deliberately unchanged, so models.py keeps matching the databases.

    These six redundant indexes exist on BOTH lineages, so they are not drift.
    Removing them from the model now — without a migration dropping them from
    the databases — would manufacture new drift in the opposite direction. They
    go together, in their own cleanup revision.
    """
    engine = _fresh(tmp_path)
    inspector = inspect(engine)
    for table in (
        "aianalysis",
        "screenshots",
        "strategies",
        "trades",
        "user_settings",
        "weekly_reviews",
    ):
        names = {i["name"] for i in inspector.get_indexes(table)}
        assert f"ix_{table}_id" in names, (
            f"ix_{table}_id was removed from the model without a migration "
            f"dropping it from the databases"
        )


# ---------------------------------------------------------------------------
# One copy of the DDL
# ---------------------------------------------------------------------------


def test_the_revision_and_the_script_share_one_implementation():
    """Two independently maintained copies of this DDL would drift apart."""
    revision = (
        _REPO / "alembic" / "versions" / "t0u1v2w3x4y5_adopt_schema_divergence.py"
    ).read_text()
    script = (_REPO / "scripts" / "adopt_schema.py").read_text()

    assert "from src.tradelens.db.schema_adoption import adopt" in revision
    assert "schema_adoption import" in script

    # upgrade() must delegate. Asserted on the parsed call rather than a literal
    # string so that renaming the local bind variable does not read as a
    # regression — the contract is "it calls adopt", not how it spells the arg.
    upgrade_fn = next(
        n
        for n in ast.walk(ast.parse(revision))
        if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    )
    calls = {
        n.func.id
        for n in ast.walk(upgrade_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "adopt" in calls, "upgrade() must delegate to schema_adoption.adopt"

    # Neither may carry its own DDL. Comments are stripped first: the prose in
    # upgrade() explaining why SQLite is skipped necessarily names the statements
    # SQLite cannot express, and that must not read as a violation.
    def executable_lines(text_: str) -> str:
        return "\n".join(
            line for line in text_.splitlines() if not line.lstrip().startswith("#")
        )

    bodies = (
        ("revision upgrade()", ast.get_source_segment(revision, upgrade_fn) or ""),
        ("script", script),
    )
    for name, body in bodies:
        code = executable_lines(body)
        for ddl in ("CREATE UNIQUE INDEX", "ADD CONSTRAINT", "SET DEFAULT"):
            assert (
                ddl not in code
            ), f"{name} carries its own {ddl} instead of calling schema_adoption"


def test_the_auth_revision_follows_the_adoption_revision():
    source = (
        _REPO / "alembic" / "versions" / "s9t0u1v2w3x4_add_site_auth_and_onboarding.py"
    ).read_text()
    assert 'down_revision: Union[str, Sequence[str], None] = "t0u1v2w3x4y5"' in source

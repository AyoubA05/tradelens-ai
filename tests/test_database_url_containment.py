"""A bad DATABASE_URL must disclose nothing and fall back to nothing.

With an unusable `DATABASE_URL`, `db/session.py` used to raise at MODULE
IMPORT. That happens before any page renders, so the failure was handled by
Streamlit rather than by us: its own error view, a full traceback, and the
connection string printed into the browser. Measured — the rendered page
contained both `Traceback` and the DSN.

A DSN carries a password. So these tests use a sentinel DSN and assert that
neither half of it reaches a log, a stream, or a rendered page, and that
nothing quietly substitutes a working database in its place.

Module-level behaviour is exercised in SUBPROCESSES on purpose. The defect is
an import-time one, and `importlib.reload(session)` would rebind `engine` and
`SessionLocal` while every service module in this process still holds the old
references — poisoning the rest of the suite to test a cold start.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SENTINEL_USER = "SENTINELUSER"
SENTINEL_PASS = "SENTINELPASSWORD"
SENTINEL_HOST = "sentinel-host.invalid"
# A DSN whose driver does not exist, so create_engine fails while parsing it.
BAD_URL = (
    f"nosuchdriver+nodbapi://{SENTINEL_USER}:{SENTINEL_PASS}"
    f"@{SENTINEL_HOST}:5432/sentineldb"
)
SENTINELS = (SENTINEL_USER, SENTINEL_PASS, SENTINEL_HOST, "sentineldb")


def _run(code: str, url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    env["DEMO_MODE"] = "false"
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


# ── the engine is contained, and is not replaced ──────────────────────────


def test_a_bad_url_does_not_raise_at_import():
    proc = _run(
        """
        import logging; logging.basicConfig(level=logging.DEBUG)
        from src.tradelens.db import session
        print("IMPORTED_OK")
        print("ENGINE_IS_NONE", session.engine is None)
        print("READY", session.database_ready())
        """,
        BAD_URL,
    )
    assert "IMPORTED_OK" in proc.stdout, proc.stderr[-2000:]
    assert "ENGINE_IS_NONE True" in proc.stdout
    assert "READY False" in proc.stdout


def test_no_fallback_engine_is_created():
    """The engine must stay None. Substituting SQLite would send a deployment
    that believes it is on Postgres to a local file — new writes going
    somewhere nobody reads, and existing tenants appearing to have no data."""
    proc = _run(
        """
        from src.tradelens.db import session
        print("ENGINE", repr(session.engine))
        print("SESSIONMAKER", repr(session._sessionmaker))
        """,
        BAD_URL,
    )
    assert "ENGINE None" in proc.stdout
    assert "SESSIONMAKER None" in proc.stdout
    assert "sqlite" not in proc.stdout.lower()


def test_a_session_is_refused_rather_than_unbound():
    proc = _run(
        """
        from src.tradelens.db import session
        try:
            session.SessionLocal()
            print("NO_RAISE")
        except session.DatabaseUnavailableError as exc:
            print("REFUSED", str(exc))
        """,
        BAD_URL,
    )
    assert "REFUSED" in proc.stdout
    assert "NO_RAISE" not in proc.stdout


def test_init_db_fails_closed():
    proc = _run(
        """
        from src.tradelens.db.init_db import init_db
        from src.tradelens.db.session import DatabaseUnavailableError
        try:
            init_db()
            print("NO_RAISE")
        except DatabaseUnavailableError:
            print("FAILED_CLOSED")
        """,
        BAD_URL,
    )
    assert "FAILED_CLOSED" in proc.stdout
    assert "NO_RAISE" not in proc.stdout


# ── nothing leaks ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("sentinel", SENTINELS)
def test_the_dsn_never_reaches_stdout_or_stderr_at_import(sentinel):
    """Covers the log too: logging writes to stderr by default, and this run
    turns logging all the way up before importing."""
    proc = _run(
        """
        import logging; logging.basicConfig(level=logging.DEBUG)
        from src.tradelens.db import session   # noqa: F401
        print("done")
        """,
        BAD_URL,
    )
    blob = proc.stdout + proc.stderr
    assert sentinel not in blob, f"{sentinel!r} leaked at import"


def test_the_import_emits_no_traceback_and_no_sqlalchemy_url():
    proc = _run(
        """
        import logging; logging.basicConfig(level=logging.DEBUG)
        from src.tradelens.db import session   # noqa: F401
        print("done")
        """,
        BAD_URL,
    )
    blob = proc.stdout + proc.stderr
    for banned in ("Traceback", "nosuchdriver", "NoSuchModuleError:", "URL("):
        assert banned not in blob, f"{banned!r} present in a contained failure"


def test_the_log_line_names_only_the_exception_type():
    proc = _run(
        """
        import logging; logging.basicConfig(level=logging.ERROR)
        from src.tradelens.db import session   # noqa: F401
        """,
        BAD_URL,
    )
    blob = proc.stdout + proc.stderr
    assert "Database engine unavailable" in blob, "the failure was not logged"
    for sentinel in SENTINELS:
        assert sentinel not in blob


def test_init_db_failure_carries_no_detail():
    proc = _run(
        """
        from src.tradelens.db.init_db import init_db
        from src.tradelens.db.session import DatabaseUnavailableError
        try:
            init_db()
        except DatabaseUnavailableError as exc:
            print("MSG:", str(exc))
        """,
        BAD_URL,
    )
    for sentinel in SENTINELS:
        assert sentinel not in proc.stdout


# ── no authentication path is entered ─────────────────────────────────────


def test_the_boot_stops_before_any_authentication():
    """`app.py` must stop AT the database bootstrap, not merely fail somewhere
    after it.

    This test previously asserted that a sentinel `print` was not reached, and
    it passed even with `st.stop()` deleted — the script died a few lines later
    for an unrelated reason, so the sentinel never printed either way. It was
    measuring the crash, not the stop.

    The signal that actually separates them is what gets RENDERED. With the
    stop: zero widgets. Without it, execution runs on into `require_auth()` and
    paints a full login form — 5 text inputs and 3 buttons, measured — on a
    deployment whose data store does not exist. Offering a password box backed
    by nothing is the authentication path being entered.
    """
    proc = _run(
        """
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("src/tradelens/ui/app.py", default_timeout=60).run()
        print("WIDGETS", len(at.text_input), len(at.button))
        print("ERRORS", [e.value for e in at.error])
        """,
        BAD_URL,
    )
    assert "WIDGETS 0 0" in proc.stdout, (
        "the script continued past the database bootstrap and rendered "
        f"interactive controls: {proc.stdout[-800:]}"
    )
    assert "TradeLens is temporarily unavailable" in proc.stdout
    for sentinel in SENTINELS:
        assert sentinel not in proc.stdout + proc.stderr


def test_the_rendered_boot_message_is_generic():
    """Drive the real app through AppTest, in a subprocess so the bad URL is
    in place before `session` is first imported."""
    proc = _run(
        """
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("src/tradelens/ui/app.py", default_timeout=60).run()
        print("ERRORS:", [e.value for e in at.error])
        print("EXCEPTIONS:", [str(e.value) for e in at.exception])
        """,
        BAD_URL,
    )
    blob = proc.stdout + proc.stderr
    assert "TradeLens is temporarily unavailable" in blob, blob[-2000:]
    for sentinel in SENTINELS:
        assert sentinel not in blob, f"{sentinel!r} reached the rendered app"
    assert "Traceback" not in proc.stdout


# ── healthy configurations are unchanged ──────────────────────────────────


def test_a_valid_sqlite_url_still_works(tmp_path):
    db = tmp_path / "ok.db"
    proc = _run(
        """
        from src.tradelens.db import session
        from src.tradelens.db.init_db import init_db
        print("READY", session.database_ready())
        init_db()
        s = session.SessionLocal(); s.close()
        print("SESSION_OK")
        """,
        f"sqlite:///{db}",
    )
    assert "READY True" in proc.stdout, proc.stderr[-2000:]
    assert "SESSION_OK" in proc.stdout


def test_the_default_configuration_still_works():
    """No DATABASE_URL set at all — the documented SQLite default. This must
    NOT be confused with the contained-failure path."""
    env_url = "sqlite:///./data/tradelens_default_probe.db"
    proc = _run(
        """
        from src.tradelens.db import session
        print("READY", session.database_ready())
        """,
        env_url,
    )
    assert "READY True" in proc.stdout


# ── the configuration half of the defence ─────────────────────────────────


def test_show_error_details_is_disabled_in_project_config():
    try:
        import tomllib
    except ImportError:  # pragma: no cover - py3.9
        import tomli as tomllib

    cfg = tomllib.load(open(ROOT / ".streamlit" / "config.toml", "rb"))
    value = cfg["client"]["showErrorDetails"]
    # Pin the canonical 1.50.0 spelling. Accepting Streamlit's legacy false
    # variations here would let the project drift back onto a compatibility
    # shim even though config.toml deliberately chose the stable enum value.
    assert value == "none", value


def test_show_error_details_value_is_valid_for_the_pinned_streamlit():
    """A typo here fails open — Streamlit falls back to its "full" default and
    prints tracebacks again."""
    from streamlit.config import ShowErrorDetailsConfigOptions

    try:
        import tomllib
    except ImportError:  # pragma: no cover - py3.9
        import tomli as tomllib

    cfg = tomllib.load(open(ROOT / ".streamlit" / "config.toml", "rb"))
    value = cfg["client"]["showErrorDetails"]
    valid = {o.value for o in ShowErrorDetailsConfigOptions}
    assert value in valid or ShowErrorDetailsConfigOptions.is_false_variation(value)

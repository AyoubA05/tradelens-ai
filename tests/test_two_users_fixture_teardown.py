"""Guards the `two_users` fixture's own cleanup.

`two_users` (in the root conftest.py) reloads `tl_config` / `db_session` /
`db_models` / `users` to point at a tmp-path SQLite database for the duration
of one test. If it left those modules pointing at the tmp path afterward,
every later test that does not patch its own `SessionLocal` would silently
run against a database file that tmp_path has already deleted — a shared-state
bug that looks identical to a passing suite until the wrong test runs after
it. This proves the fixture restores the original engine, not just that it
built a working tmp one.

Order matters here: these two tests must run in this order (pytest executes a
module's tests in declaration order), so the second one observes whatever the
first one's fixture teardown left behind.
"""

from src.tradelens.db import session as db_session

# `two_users` reloads db_models against whatever `Base` db_session currently
# holds. In the full suite db_models is always already imported by some
# earlier-collected test module before any test using `two_users` runs, so
# its `class User(Base)` only ever executes once per reload. This file is the
# first to import db_session without also importing db_models, so import it
# here too — otherwise the fixture's own `from ... import models as
# db_models; importlib.reload(db_models)` would execute the module body
# twice back to back (a plain first-time import, then an immediate reload)
# and crash on "Table 'users' is already defined", which is an artifact of
# this file's import order, not a real defect in the fixture.
from src.tradelens.db import models as db_models  # noqa: F401

_ORIGINAL_ENGINE_URL = str(db_session.engine.url)


def test_two_users_points_the_engine_at_a_tmp_db(two_users):
    # Sanity check that the fixture really did repoint the engine — otherwise
    # the "restored" assertion below would be trivially true for the wrong
    # reason (it never moved).
    assert str(db_session.engine.url) != _ORIGINAL_ENGINE_URL


def test_engine_is_restored_after_two_users_teardown():
    """Runs after the test above. The `two_users` teardown must have put
    `db_session.engine` back on the original DATABASE_URL, or every test
    collected after a `two_users` test in the full suite would be running
    against a deleted tmp database."""
    assert str(db_session.engine.url) == _ORIGINAL_ENGINE_URL

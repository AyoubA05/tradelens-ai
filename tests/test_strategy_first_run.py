"""First-run Strategy Profile: atomic completion, and who the gate applies to.

Two things are worth proving here and neither is provable from the page source.

The first is the failure ordering. ``save_profile_and_mark_completed`` writes a
profile and flips ``users.strategy_profile_completed`` in one transaction
precisely so the account cannot end up flagged complete with nothing behind it —
that user would be routed past the first-run screen forever, to a dashboard
whose reviews have no rules to read. A test that only checks the happy path
would pass just as well against two independent commits.

The second is scope. The gate redirects site-authenticated arrivals only.
Legacy accounts were backfilled from whether a Strategy row happened to exist,
so applying the gate to them would start bouncing old accounts off their own
dashboard because of a rollout they never joined.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, Strategy, User


@pytest.fixture()
def db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    for module in ("strategy", "users"):
        monkeypatch.setattr(
            f"src.tradelens.services.{module}.SessionLocal", TestSession
        )
    return TestSession


def _user(db, **flags) -> int:
    session = db()
    user = User(
        username="first-run",
        password_hash="hash",
        strategy_profile_completed=flags.get("completed", False),
    )
    session.add(user)
    session.commit()
    uid = user.id
    session.close()
    return uid


class FakeSt:
    """Enough of the Streamlit object for the gate: state and a page switch."""

    def __init__(self, **state):
        self.session_state = dict(state)
        self.switched_to = None

    def switch_page(self, page):
        self.switched_to = page


# ---------------------------------------------------------------------------
# The atomic write
# ---------------------------------------------------------------------------


def test_saving_a_playbook_also_completes_the_first_run_step(db):
    from src.tradelens.services.strategy import save_profile_and_mark_completed
    from src.tradelens.services.users import get_onboarding_state

    uid = _user(db)
    assert get_onboarding_state(uid)["strategy_profile_completed"] is False

    saved = save_profile_and_mark_completed(uid, name="Asia Range", markets="NQ")

    assert saved["name"] == "Asia Range"
    assert saved["is_active"] == 1
    assert get_onboarding_state(uid)["strategy_profile_completed"] is True


def test_a_failed_profile_write_leaves_the_account_incomplete(db, monkeypatch):
    """The ordering that matters: no completion flag without a playbook.

    The failure is forced *after* the profile row is populated and before the
    commit, which is the only window where a two-transaction implementation
    would already have written one of the two.
    """
    from src.tradelens.services import strategy as service
    from src.tradelens.services.users import get_onboarding_state

    uid = _user(db)

    real = service._upsert_in_session

    def explode(session, user_id, fields):
        real(session, user_id, fields)
        raise RuntimeError("driver died mid-write")

    monkeypatch.setattr(service, "_upsert_in_session", explode)

    with pytest.raises(RuntimeError):
        service.save_profile_and_mark_completed(uid, name="Asia Range")

    assert get_onboarding_state(uid)["strategy_profile_completed"] is False
    session = db()
    assert session.query(Strategy).count() == 0
    session.close()


def test_a_missing_account_writes_no_profile(db):
    """The flag update and the profile share a transaction in both directions."""
    from src.tradelens.services.strategy import save_profile_and_mark_completed

    with pytest.raises(ValueError):
        save_profile_and_mark_completed(999_999, name="Ghost")

    session = db()
    assert session.query(Strategy).count() == 0
    session.close()


def test_the_plain_upsert_still_does_not_touch_the_flag(db):
    """Analytics' "add to profile" and the seeder use it; neither is a first run."""
    from src.tradelens.services.strategy import upsert_strategy_profile
    from src.tradelens.services.users import get_onboarding_state

    uid = _user(db)
    upsert_strategy_profile(uid, name="Asia Range")

    assert get_onboarding_state(uid)["strategy_profile_completed"] is False


def test_completing_twice_is_not_an_error(db):
    from src.tradelens.services.strategy import save_profile_and_mark_completed
    from src.tradelens.services.users import get_onboarding_state

    uid = _user(db)
    save_profile_and_mark_completed(uid, name="First")
    saved = save_profile_and_mark_completed(uid, name="Second")

    assert saved["name"] == "Second"
    assert get_onboarding_state(uid)["strategy_profile_completed"] is True
    session = db()
    assert session.query(Strategy).count() == 1
    session.close()


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_a_site_authenticated_first_timer_is_redirected(db):
    from src.tradelens.ui.components.strategy_gate import (
        STRATEGY_PAGE,
        enforce_first_run,
        is_first_run,
    )

    uid = _user(db)
    st = FakeSt(_site_auth_user_id=uid)

    assert enforce_first_run(st, uid) is True
    assert st.switched_to == STRATEGY_PAGE
    assert is_first_run(st) is True


def test_a_completed_account_is_left_on_the_dashboard(db):
    from src.tradelens.ui.components.strategy_gate import (
        enforce_first_run,
        is_first_run,
    )

    uid = _user(db, completed=True)
    st = FakeSt(_site_auth_user_id=uid)

    assert enforce_first_run(st, uid) is False
    assert st.switched_to is None
    assert is_first_run(st) is False


def test_a_legacy_session_is_never_redirected(db):
    """No ``_site_auth_user_id``, so this is the username/password path."""
    from src.tradelens.ui.components.strategy_gate import enforce_first_run

    uid = _user(db)
    st = FakeSt()

    assert enforce_first_run(st, uid) is False
    assert st.switched_to is None


def test_a_routing_failure_does_not_take_down_the_dashboard(db):
    """A registry-less boot cannot switch pages; the page must still render."""
    from src.tradelens.ui.components.strategy_gate import enforce_first_run

    uid = _user(db)
    st = FakeSt(_site_auth_user_id=uid)

    def broken(_page):
        raise RuntimeError("no page registry")

    st.switch_page = broken

    assert enforce_first_run(st, uid) is False


def test_the_no_strategy_exit_completes_without_writing_a_profile(db):
    """Why completion is a stored flag and not "does a Strategy row exist"."""
    from src.tradelens.services.users import (
        get_onboarding_state,
        mark_strategy_profile_completed,
    )

    uid = _user(db)
    mark_strategy_profile_completed(uid)

    assert get_onboarding_state(uid)["strategy_profile_completed"] is True
    session = db()
    assert session.query(Strategy).count() == 0
    session.close()

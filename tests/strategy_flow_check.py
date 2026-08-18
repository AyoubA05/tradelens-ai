"""
Subprocess helper: drive real Strategy Profile interactions under AppTest.

Run in a child process with an isolated DB, for the same reason as
app_boot_check.py — reloading src.tradelens mid-suite creates a second copy
of ai_client and breaks every downstream `isinstance(x, AIUnavailable)`
check. Keep the subprocess boundary.

Unlike app_boot_check, this one CLICKS and TYPES, then reads the DATABASE
back. A marker test can only prove the page rendered a string; these prove
the starter template actually persisted, that a blank name is refused
before any write happens, that correcting it saves, and that saving an
edited profile leaves the fields the trader did not touch alone.

Usage:
    DATABASE_URL=sqlite:///<tmp> python strategy_flow_check.py <root> <scenario>

Exits 0 on success; nonzero with a message on failure.
"""

import sys

PAGE = "src/tradelens/ui/pages/5_Strategy.py"
UID = 1


def _account():
    """A real user row — get_active_strategy rejects a None user id."""
    from src.tradelens.db.models import User
    from src.tradelens.db.session import SessionLocal

    session = SessionLocal()
    session.add(User(id=UID, username="flow", password_hash="x"))
    session.commit()
    session.close()


def _stored():
    from src.tradelens.services.strategy import get_active_strategy

    return get_active_strategy(UID)


def _use_real_account_mode():
    """Strategy maintenance scenarios are not public-demo previews."""
    from src.tradelens.config import settings

    settings.demo_mode = False


def _app(root: str, **state):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(f"{root}/{PAGE}", default_timeout=90)
    at.session_state["authenticated"] = True
    at.session_state["current_user_id"] = UID
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def _rendered(at) -> str:
    """All user-facing page and sidebar text AppTest can inspect."""
    return "\n".join(
        [element.value for element in at.markdown]
        + [element.value for element in at.caption]
    )


def _button(at, fragment: str):
    for button in at.button:
        if fragment in button.label:
            return button
    return None


def _field(at, label: str):
    for widget in list(at.text_input) + list(at.text_area):
        if widget.label == label:
            return widget
    return None


def _save(at):
    """The form's submit. AppTest surfaces it in at.button alongside the
    ordinary ones, not under a form_submit_button element type."""
    button = _button(at, "Save playbook")
    if button is None:
        raise AssertionError("no Save playbook button")
    return button


def _flag(at, key: str) -> bool:
    """Read a session-state flag. AppTest's SafeSessionState has no .get."""
    return key in at.session_state and bool(at.session_state[key])


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def scenario_ownerless_demo_is_one_read_only_profile(root: str) -> int:
    """An ownerless legacy session never reaches the page's own preview mode.

    Every user-facing service now requires a concrete owner (Ruling 10), so
    an authenticated-but-ownerless session is refused at the shared auth gate
    before any page body — including this one's read-only sample-profile
    preview — ever runs. The refusal is what now proves no write path is
    reachable, not the page's own disabled controls.
    """
    from src.tradelens.services import strategy as strategy_service
    from src.tradelens.ui.components.auth import OWNERLESS_SESSION_MESSAGE

    def _write_without_owner(*_args, **_kwargs):
        raise AssertionError("ownerless demo attempted strategy persistence")

    real_write = strategy_service.save_profile_and_mark_completed
    strategy_service.save_profile_and_mark_completed = _write_without_owner
    try:
        at = _app(root, current_user_id=None)
    finally:
        strategy_service.save_profile_and_mark_completed = real_write

    if at.exception:
        return _fail(f"ownerless demo raised: {at.exception}")

    rendered = _rendered(at)
    if OWNERLESS_SESSION_MESSAGE not in rendered:
        return _fail("ownerless session was not refused at the auth gate")
    if "ICT/SMC Day Trading" in rendered:
        return _fail("ownerless session reached the page's own preview content")

    write_labels = {
        button.label
        for button in at.button
        if button.label in {"Apply the ICT/SMC starter playbook", "Save playbook"}
    }
    if write_labels:
        return _fail(f"ownerless demo offered write actions: {sorted(write_labels)!r}")
    strategy_fields = {
        widget.label for widget in list(at.text_input) + list(at.text_area)
    }
    if "Strategy Name" in strategy_fields:
        return _fail("ownerless demo rendered the editable strategy form")

    print("OK")
    return 0


def scenario_real_empty_account_has_collapsed_onboarding(root: str) -> int:
    """A real empty account gets one starter action and a quiet manual route."""
    _account()
    _use_real_account_mode()
    at = _app(root)
    if at.exception:
        return _fail(f"real empty account raised: {at.exception}")

    rendered = _rendered(at)
    if "No playbook yet" not in rendered or "0 of 6 sections written" not in rendered:
        return _fail("real empty account did not render its truthful empty summary")

    starter = _button(at, "Apply the ICT/SMC starter playbook")
    if starter is None:
        return _fail("real empty account has no starter save action")
    if starter.proto.type != "primary":
        return _fail(f"starter action is not primary: {starter.proto.type!r}")
    expected_help = (
        "Saves this complete starter playbook as your active profile. "
        "You can edit every rule afterward."
    )
    if starter.help != expected_help:
        return _fail(f"starter help is {starter.help!r}")

    manual = [e for e in at.expander if e.label == "Build a playbook manually"]
    if len(manual) != 1:
        return _fail(f"expected one manual onboarding expander, found {len(manual)}")
    if manual[0].proto.expanded:
        return _fail("manual onboarding is expanded by default")
    if _save(at) is None:
        return _fail("manual onboarding lost its Save playbook action")

    print("OK")
    return 0


def scenario_stored_profile_is_directly_editable(root: str) -> int:
    """Saved-profile maintenance stays open and persists through the same form."""
    result = scenario_editing_preserves_untouched_fields(root)
    if result:
        return result

    _use_real_account_mode()
    at = _app(root)
    if at.exception:
        return _fail(f"stored profile rerun raised: {at.exception}")
    if any(e.label == "Build a playbook manually" for e in at.expander):
        return _fail("saved profile maintenance was hidden behind onboarding")
    name = _field(at, "Strategy Name")
    if name is None or name.value != "Asia Range":
        return _fail(
            "saved profile fields were not rendered directly with stored values"
        )
    save = _save(at)
    if save.proto.type != "primary":
        return _fail(f"saved-profile Save action is not primary: {save.proto.type!r}")

    print("OK")
    return 0


def scenario_starter_template_persists(root: str) -> int:
    """The starter button says it saves. It has to actually save."""
    _account()
    _use_real_account_mode()
    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")
    if _stored() is not None:
        return _fail("a profile existed before the starter template was applied")

    starter = _button(at, "Apply the ICT/SMC starter playbook")
    if starter is None:
        return _fail("no starter-playbook button")

    at = starter.click().run()
    if at.exception:
        return _fail(f"applying the starter playbook raised: {at.exception}")

    saved = _stored()
    if saved is None:
        return _fail("the starter playbook was not written to the database")
    if saved.get("name") != "ICT/SMC Day Trading":
        return _fail(f"stored name is {saved.get('name')!r}")
    # It claims to be complete, so every section must in fact be written.
    for field in (
        "entry_rules",
        "stop_rules",
        "take_profit_rules",
        "risk_rules",
        "setups_traded",
        "common_mistakes",
    ):
        if not (saved.get(field) or "").strip():
            return _fail(f"starter playbook left {field} empty")
    # …and the page now reports it as complete rather than as a draft.
    rendered = [m.value for m in at.markdown] + [c.value for c in at.caption]
    if not any("6 of 6 sections written" in v for v in rendered):
        return _fail("the summary did not report a complete playbook")
    print("OK")
    return 0


def scenario_blank_name_is_refused(root: str) -> int:
    """Submitting with no name must not write, and must say so in place."""
    _account()
    _use_real_account_mode()
    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")

    at = _save(at).click().run()
    if at.exception:
        return _fail(f"submitting a blank form raised: {at.exception}")

    if _stored() is not None:
        return _fail("a blank name was written to the database")
    if not _flag(at, "_strategy_name_error"):
        return _fail("no validation state was recorded")
    rendered = [m.value for m in at.markdown]
    if not any("Strategy name is required" in v for v in rendered):
        return _fail("the validation message was not rendered")
    if not any('class="tl-field-error"' in v for v in rendered):
        return _fail("the message did not use the field-error treatment")
    if not any('role="alert"' in v for v in rendered):
        return _fail("the message was not announced")
    print("OK")
    return 0


def scenario_correcting_the_name_saves(root: str) -> int:
    """The draft survives the refusal, and the corrected form writes."""
    _account()
    _use_real_account_mode()
    at = _app(root)
    at = _save(at).click().run()
    if not _flag(at, "_strategy_name_error"):
        return _fail("expected the blank-name refusal first")

    # Fill identity AND one rule, so the completion figure has to move.
    name = _field(at, "Strategy Name")
    if name is None:
        return _fail("no Strategy Name field")
    at = name.set_value("London Continuation").run()
    entry = _field(at, "What has to be true before you enter")
    if entry is None:
        return _fail("the Entry Rules field is not reachable")
    at = entry.set_value("Sweep, then BOS on 5m").run()

    at = _save(at).click().run()
    if at.exception:
        return _fail(f"saving raised: {at.exception}")

    saved = _stored()
    if saved is None:
        return _fail("the corrected playbook was not written")
    if saved.get("name") != "London Continuation":
        return _fail(f"stored name is {saved.get('name')!r}")
    if saved.get("entry_rules") != "Sweep, then BOS on 5m":
        return _fail(f"stored entry_rules is {saved.get('entry_rules')!r}")
    if _flag(at, "_strategy_name_error"):
        return _fail("the validation error outlived the correction")

    # The save reruns, so the summary is re-read from the database.
    at = _app(root)
    rendered = [m.value for m in at.markdown]
    if not any("2 of 6 sections written" in v for v in rendered):
        return _fail("completion did not follow the saved profile")
    if not any("London Continuation" in v for v in rendered):
        return _fail("the summary did not name the saved playbook")
    print("OK")
    return 0


def scenario_editing_preserves_untouched_fields(root: str) -> int:
    """Editing one section must not blank the five the trader left alone."""
    _account()
    _use_real_account_mode()
    from src.tradelens.services.strategy import upsert_strategy_profile

    original = dict(
        name="Asia Range",
        trading_style="ICT / SMC",
        markets="NQ, ES",
        timeframes="15m entry, 4H HTF",
        entry_rules="Wait for the sweep",
        stop_rules="Behind the sweep wick",
        take_profit_rules="Opposing liquidity",
        risk_rules="1% per trade",
        setups_traded="Liquidity sweep + FVG",
        setups_avoided="News candles",
        news_session_rules="No trades around CPI",
        common_mistakes="Moving the stop",
    )
    upsert_strategy_profile(UID, **original)

    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")
    rendered = [m.value for m in at.markdown]
    if not any("6 of 6 sections written" in v for v in rendered):
        return _fail("a full profile did not report as complete")

    risk = _field(at, "How much you risk, and how often")
    if risk is None:
        return _fail("the Risk Rules field is not reachable")
    at = risk.set_value("0.5% per trade, two trades a day").run()
    at = _save(at).click().run()
    if at.exception:
        return _fail(f"saving an edit raised: {at.exception}")

    saved = _stored()
    if saved is None:
        return _fail("the edited profile disappeared")
    if saved.get("risk_rules") != "0.5% per trade, two trades a day":
        return _fail(f"the edit did not persist: {saved.get('risk_rules')!r}")
    for field, value in original.items():
        if field == "risk_rules":
            continue
        if saved.get(field) != value:
            return _fail(
                f"untouched {field} changed: {value!r} -> {saved.get(field)!r}"
            )
    print("OK")
    return 0


# A driver message of exactly the shape that must never reach a page: a
# DSN with credentials in it. SQLAlchemy puts the URL in several of its
# OperationalError strings, so this is the realistic leak, not a contrived
# one.
_LEAKY = (
    "could not connect to server: connection refused\n"
    "(Background on this error at: https://sqlalche.me/e/20/e3q8)\n"
    "postgresql://tl_admin:pr0d-p4ssw0rd-9f3a@db.internal:5432/tradelens"
)
_SECRETS = ("tl_admin", "pr0d-p4ssw0rd-9f3a", "db.internal", "postgresql://")


def scenario_starter_write_failure_is_contained(root: str) -> int:
    """The starter write fails with a credential-bearing driver message.

    The page must survive it, say something the trader can act on, leak
    none of it, and leave the database exactly as it found it — both when
    there is no playbook yet and when there is one to protect.
    """
    _account()
    _use_real_account_mode()

    def _explode(*_args, **_kwargs):
        raise RuntimeError(_LEAKY)

    # Patch the service BEFORE AppTest imports the page: the page does
    # `from ...strategy import save_profile_and_mark_completed`, so it binds
    # whatever the module holds at import time, on every run.
    from src.tradelens.services import strategy as strategy_service

    real_upsert = strategy_service.upsert_strategy_profile
    real_write = strategy_service.save_profile_and_mark_completed
    strategy_service.save_profile_and_mark_completed = _explode

    def _click_starter():
        at = _app(root)
        if at.exception:
            return None, f"initial run raised: {at.exception}"
        starter = _button(at, "Apply the ICT/SMC starter playbook")
        if starter is None:
            return None, "no starter-playbook button"
        return starter.click().run(), None

    def _check(at):
        # 1. the page survived
        if at.exception:
            return f"the failure escaped to the page: {at.exception}"
        rendered = [m.value for m in at.markdown] + [c.value for c in at.caption]
        page = "\n".join(rendered)
        # 2. a recovery message the trader can act on
        if "Could not save the playbook. Try again." not in page:
            return "no generic recovery message was rendered"
        # 3. …and none of the driver's text
        for secret in _SECRETS:
            if secret in page:
                return f"the page leaked {secret!r}"
        if "RuntimeError" in page or "Traceback" in page:
            return "the page leaked the exception type or a traceback"
        return None

    try:
        # --- with no playbook yet: nothing may be created
        at, failure = _click_starter()
        if failure:
            return _fail(failure)
        problem = _check(at)
        if problem:
            return _fail(problem)
        if _stored() is not None:
            return _fail("a failed starter write created a profile row")

        # --- with a playbook already saved: it must be untouched.
        # Seeded through the plain upsert, which was never patched, so the
        # page's write stays exploded for the click that follows.
        existing = dict(
            name="Asia Range",
            trading_style="ICT / SMC",
            markets="NQ, ES",
            entry_rules="Wait for the sweep",
            risk_rules="1% per trade",
        )
        real_upsert(UID, **existing)
        before = _stored()
        strategy_service.save_profile_and_mark_completed = _explode

        at, failure = _click_starter()
        if failure:
            return _fail(failure)
        problem = _check(at)
        if problem:
            return _fail(problem)

        after = _stored()
        if after is None:
            return _fail("a failed starter write destroyed the existing playbook")
        for field, value in existing.items():
            if after.get(field) != value:
                return _fail(
                    f"existing {field} changed: {value!r} -> {after.get(field)!r}"
                )
        if after.get("updated_at") != before.get("updated_at"):
            return _fail("a failed starter write still touched the row")
    finally:
        strategy_service.save_profile_and_mark_completed = real_write

    print("OK")
    return 0


_SCENARIOS = {
    "ownerless_demo_is_one_read_only_profile": scenario_ownerless_demo_is_one_read_only_profile,
    "real_empty_account_has_collapsed_onboarding": scenario_real_empty_account_has_collapsed_onboarding,
    "starter_write_failure_is_contained": scenario_starter_write_failure_is_contained,
    "starter_template_persists": scenario_starter_template_persists,
    "blank_name_is_refused": scenario_blank_name_is_refused,
    "correcting_the_name_saves": scenario_correcting_the_name_saves,
    "editing_preserves_untouched_fields": scenario_editing_preserves_untouched_fields,
    "stored_profile_is_directly_editable": scenario_stored_profile_is_directly_editable,
}


def main() -> int:
    root, scenario = sys.argv[1:3]
    sys.path.insert(0, root)

    try:
        import streamlit as st

        st.secrets._secrets = {}
    except Exception:  # noqa: BLE001 — must run even if this internal changes
        pass

    from src.tradelens.db.init_db import init_db

    init_db()
    return _SCENARIOS[scenario](root)


if __name__ == "__main__":
    sys.exit(main())

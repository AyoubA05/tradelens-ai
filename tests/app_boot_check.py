"""
Subprocess helper: boot a Streamlit page under AppTest with an ISOLATED DB.

Run in a child process (not collected by pytest — no test_ prefix) so module
state and the DATABASE_URL engine are fully isolated from the parent suite. This
realizes "env var before import": DATABASE_URL is set in the child's environment
before any src.tradelens module is imported, so the engine binds to the tmp DB
with no post-import SessionLocal monkeypatching.

⚠️  DO NOT "optimize" this back into an in-process pytest fixture (e.g. setting
DATABASE_URL then purging src.tradelens.* from sys.modules and re-importing).
That is a known Streamlit-testing trap: reloading the package mid-suite creates a
SECOND copy of ai_client, so every downstream `isinstance(x, AIUnavailable)`
check in other test files (which bound those symbols at collection time) fails.
We measured 34–47 spurious failures doing exactly that. A subprocess is the
correct, suite-safe isolation boundary. Keep it.

Usage:
    DATABASE_URL=sqlite:///<tmp> python app_boot_check.py <root> <app> <marker> <0|1>

Exits 0 on success; nonzero with a message on failure.
"""

import json as _json
import sys

# The default owner for seeded boot data. Every user-facing service now
# requires a concrete owner (Ruling 10), so a page booted with no owner in
# session state is refused at require_auth() before it ever reads a trade —
# this constant is what makes the *seeded* boots (the overwhelming majority
# of callers) exercise the real, signed-in path instead. A caller that wants
# to boot genuinely ownerless (to prove the refusal itself) passes an explicit
# ``"current_user_id": null`` in its preset, which overrides this default.
DEFAULT_SEED_UID = 1


def main() -> int:
    root, app_path, marker, seed = sys.argv[1:5]
    # Optional 5th arg: JSON session state, applied before the first run.
    # Lets a caller boot a page in a specific state (a Journal view, a
    # selected trade) without the runner knowing anything about that page.
    preset = sys.argv[5] if len(sys.argv) > 5 else "{}"
    preset_state = _json.loads(preset)
    # Resolve the seed owner BEFORE any Trade rows are inserted below, so
    # seeded data is owned by whichever session the AppTest will actually run
    # as. An explicit (including null) "current_user_id" in the preset wins;
    # otherwise every boot defaults to a real, signed-in owner.
    seed_uid = (
        preset_state["current_user_id"]
        if "current_user_id" in preset_state
        else DEFAULT_SEED_UID
    )
    sys.path.insert(0, root)

    # Isolate from a developer's real .streamlit/secrets.toml BEFORE config is
    # imported. Streamlit exports top-level secrets into os.environ on first
    # access, which would otherwise override DEMO_MODE=true and leak a real API
    # key — letting auto-running AI pages (Insights & Review) make live calls
    # during a boot test. Pinning _secrets to {} stops the file load entirely.
    try:
        import streamlit as st

        st.secrets._secrets = {}
    except Exception:  # noqa: BLE001 — boot tests must run even if this changes
        pass

    from src.tradelens.db.init_db import init_db

    init_db()

    if seed == "fixedrisk":
        # Several dated trades that all risked the SAME amount. A "risk per
        # trade" line through one repeated value is a flat rule drawn at
        # full height, so the page must state the constant instead.
        # A separate seed, not a change to "1": the other boots assert
        # behaviour that depends on that fixture staying as it is.
        from src.tradelens.db.models import Trade
        from src.tradelens.db.session import SessionLocal

        session = SessionLocal()
        session.add_all(
            [
                Trade(
                    trade_date=f"2026-06-{day:02d}",
                    asset="NQ",
                    direction="Long",
                    result="Win" if pnl > 0 else "Loss",
                    pnl=pnl,
                    risk_amount=125.0,
                    rr_realized=pnl / 125.0,
                    setup_type="BOS + FVG",
                    killzone="ny_am",
                    session="New York",
                    user_id=seed_uid,
                )
                for day, pnl in (
                    (15, 250.0),
                    (16, -125.0),
                    (17, 375.0),
                    (18, -125.0),
                    (19, 125.0),
                )
            ]
        )
        session.commit()
        session.close()

    if seed == "one":
        # Exactly one trade: the low-data case. Charts must be withheld.
        from src.tradelens.db.models import Trade
        from src.tradelens.db.session import SessionLocal

        s = SessionLocal()
        s.add(
            Trade(
                trade_date="2026-06-15",
                asset="NQ",
                direction="Long",
                result="Loss",
                pnl=-500.0,
                killzone="ny_am",
                user_id=seed_uid,
            )
        )
        s.commit()
        s.close()

    if seed == "onecategory":
        # Enough trades to rank, but only ONE session, ONE weekday and ONE
        # setup. Nothing here has anything to be "strongest" of, and the
        # setup name carries an ampersand so double-escaping would show.
        from src.tradelens.db.models import Trade
        from src.tradelens.db.session import SessionLocal

        session = SessionLocal()
        session.add_all(
            [
                Trade(
                    # every date is a Monday, so day-of-week has one value
                    trade_date=day,
                    asset="NQ",
                    direction="Long",
                    result="Win" if pnl > 0 else "Loss",
                    pnl=pnl,
                    rr_realized=pnl / 100.0,
                    setup_type="BOS & FVG",
                    killzone="ny_am",
                    session="New York",
                    user_id=seed_uid,
                )
                for day, pnl in (
                    ("2026-06-01", 200.0),
                    ("2026-06-08", -100.0),
                    ("2026-06-15", 300.0),
                    ("2026-06-22", -100.0),
                    ("2026-06-29", 150.0),
                    ("2026-07-06", 250.0),
                )
            ]
        )
        session.commit()
        session.close()

    if seed == "profile":
        # A real user with a saved, partially-filled strategy profile. The
        # Strategy page reads it through get_active_strategy(uid), which
        # rejects a None user id, so the row and the account both have to
        # exist — and the caller must preset current_user_id in state.
        from src.tradelens.db.models import User
        from src.tradelens.db.session import SessionLocal
        from src.tradelens.services.strategy import upsert_strategy_profile

        s = SessionLocal()
        s.add(User(id=seed_uid, username="booter", password_hash="x"))
        s.commit()
        s.close()
        upsert_strategy_profile(
            seed_uid,
            name="ICT Continuation",
            trading_style="ICT / SMC",
            markets="NQ, ES",
            timeframes="15m entry, 4H HTF",
            entry_rules="BOS then OB retest",
            # exit, risk, setups and self-awareness deliberately left empty so
            # the completion figure has something to be less than.
        )

    if seed == "1":
        from src.tradelens.db.models import Trade
        from src.tradelens.db.session import SessionLocal

        s = SessionLocal()
        s.add_all(
            [
                Trade(
                    trade_date="2026-06-15",
                    asset="NQ",
                    direction="Long",
                    result="Win",
                    pnl=200.0,
                    ai_grade="A",
                    killzone="ny_am",
                    user_id=seed_uid,
                ),
                Trade(
                    trade_date="2026-06-16",
                    asset="ES",
                    direction="Short",
                    result="Loss",
                    pnl=-90.0,
                    ai_grade="C",
                    killzone="london",
                    user_id=seed_uid,
                ),
            ]
        )
        s.commit()
        s.close()

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(app_path)
    at.session_state["authenticated"] = True  # bypass the login gate during boot
    # Same default as the seeded data above, so a boot with no explicit
    # preset lands on the owner its own seed rows were stamped with. A
    # caller wanting the ownerless refusal path overrides this explicitly.
    at.session_state["current_user_id"] = seed_uid

    for _key, _value in preset_state.items():
        at.session_state[_key] = _value
    at = at.run()
    if at.exception:
        print(f"app raised: {at.exception}", file=sys.stderr)
        return 2

    # marker == "-" means boot-only: assert no exception, skip the content check.
    # A "no-charts:" prefix additionally asserts the page drew zero Plotly
    # canvases — the low-data contract.
    assert_no_charts = marker.startswith("no-charts:")
    if assert_no_charts:
        marker = marker[len("no-charts:") :]

    if marker != "-":
        # Captions are their own element type in AppTest, not markdown, and
        # plenty of user-facing copy (empty-state guidance, demo notices)
        # is written with st.caption.
        rendered = [m.value for m in at.markdown] + [c.value for c in at.caption]
        if not any(marker in v for v in rendered):
            print(f"marker not found: {marker}", file=sys.stderr)
            return 3

    if assert_no_charts:
        charts = at.get("plotly_chart")
        if charts:
            print(f"expected no charts, found {len(charts)}", file=sys.stderr)
            return 4

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

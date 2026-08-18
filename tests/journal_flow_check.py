"""
Subprocess helper: drive real Journal interactions under AppTest.

Run in a child process with an isolated DB, for the same reason as
app_boot_check.py — reloading src.tradelens mid-suite creates a second copy
of ai_client and breaks every downstream `isinstance(x, AIUnavailable)`
check. Keep the subprocess boundary.

Unlike app_boot_check, this one CLICKS: it walks the ledger → detail → back
round trip and the calendar → day → detail path, which is where the
Streamlit widget-key crash lived. Boot tests cannot reach those states,
because they set session state before the first run — precisely the case
Streamlit allows.

Usage:
    DATABASE_URL=sqlite:///<tmp> python journal_flow_check.py <root> <scenario>

Exits 0 on success; nonzero with a message on failure.
"""

import sys

PAGE = "src/tradelens/ui/pages/2_Trades.py"


BOOT_UID = 1


def _seed():
    """Three dated trades on two days, so a calendar day has two openers."""
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    session = SessionLocal()
    session.add_all(
        [
            Trade(
                trade_date="2026-06-15",
                asset="NQ",
                direction="Long",
                result="Win",
                pnl=200.0,
                rr_realized=2.0,
                setup_type="BOS + FVG",
                killzone="ny_am",
                session="New York",
                user_id=BOOT_UID,
            ),
            Trade(
                trade_date="2026-06-15",
                asset="ES",
                direction="Short",
                result="Loss",
                pnl=-90.0,
                rr_realized=-1.0,
                setup_type="FVG + OB",
                killzone="london_open",
                session="London",
                user_id=BOOT_UID,
            ),
            Trade(
                trade_date="2026-06-16",
                asset="GBP/USD",
                direction="Long",
                result="Breakeven",
                pnl=0.0,
                rr_realized=0.0,
                setup_type="CHoCH Entry",
                killzone="asia",
                session="Asian",
                user_id=BOOT_UID,
            ),
        ]
    )
    session.commit()
    ids = [t.id for t in session.query(Trade).order_by(Trade.id).all()]
    session.close()
    return ids


def _app(root: str, **state):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(f"{root}/{PAGE}", default_timeout=90)
    at.session_state["authenticated"] = True
    # Every user-facing service now requires a concrete owner (Ruling 10); an
    # ownerless session is refused at the shared auth gate before this page
    # ever renders. Boot signed in as the same owner the seed data is under.
    at.session_state["current_user_id"] = BOOT_UID
    # A window that comfortably contains the seeded dates.
    at.session_state["jf_from"] = __import__("datetime").date(2026, 6, 1)
    at.session_state["jf_to"] = __import__("datetime").date(2026, 6, 30)
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def _button(at, fragment: str):
    for button in at.button:
        if fragment in button.label:
            return button
    return None


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def scenario_row_to_detail_and_back(root: str, ids) -> int:
    """Ledger row → Trade Detail → Back → ledger, with identity preserved."""
    target = ids[0]
    # A ledger row selection is a dataframe event, which AppTest cannot
    # synthesise; the page's own selectbox drives the identical code path
    # (_open_trade → intent → rerun), so it is what gets exercised here.
    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")
    if at.session_state["journal_view"] != "Trades":
        return _fail("did not open on the ledger")

    picker = next((s for s in at.selectbox if s.label == "Open a trade"), None)
    if picker is None:
        return _fail("no trade picker on the ledger view")
    at = picker.select(target).run()
    if at.exception:
        return _fail(f"opening a trade raised: {at.exception}")

    if at.session_state["journal_view"] != "Trade Detail":
        return _fail(f"view is {at.session_state['journal_view']!r}, not Trade Detail")
    if at.session_state["selected_trade_id"] != target:
        return _fail("selected trade identity did not survive the transition")

    back = _button(at, "Back to trades")
    if back is None:
        return _fail("no back path out of Trade Detail")
    at = back.click().run()
    if at.exception:
        return _fail(f"going back raised: {at.exception}")
    if at.session_state["journal_view"] != "Trades":
        return _fail("Back did not return to the ledger")
    # …and it must not bounce straight back into the detail.
    if _button(at, "Back to trades") is not None:
        return _fail("Back bounced into Trade Detail again")
    print("OK")
    return 0


def scenario_calendar_day_to_detail(root: str, ids) -> int:
    """Calendar → select a day → open one of that day's trades."""
    at = _app(root, journal_view="Calendar")
    if at.exception:
        return _fail(f"calendar view raised: {at.exception}")

    day = _button(at, "15")
    if day is None:
        return _fail("no calendar day button for the seeded date")
    at = day.click().run()
    if at.exception:
        return _fail(f"selecting a day raised: {at.exception}")

    openers = [b for b in at.button if b.key and b.key.startswith("journal_calopen_")]
    if len(openers) != 2:
        return _fail(f"expected 2 openers for 2026-06-15, found {len(openers)}")

    target = int(openers[0].key.rsplit("_", 1)[1])
    at = openers[0].click().run()
    if at.exception:
        return _fail(f"opening a day trade raised: {at.exception}")
    if at.session_state["journal_view"] != "Trade Detail":
        return _fail("calendar opener did not reach Trade Detail")
    if at.session_state["selected_trade_id"] != target:
        return _fail("calendar opener opened the wrong trade")
    if _button(at, "Back to trades") is None:
        return _fail("no back path from a calendar-opened trade")
    print("OK")
    return 0


def scenario_summary_markdown(root: str, ids) -> int:
    """The generated summary keeps Markdown semantics.

    Rendered through render_editorial_readout, the document's headings and
    lists are escaped into literal ### and - characters inside one HTML
    string. Rendered by Streamlit, they arrive as their own Markdown element
    with unsafe HTML off.
    """
    document = (
        "### What worked\n\n"
        "- Held the London session plan\n"
        "- **Stops** left alone\n\n"
        "### What to watch\n\n"
        "1. Late entries after the sweep\n"
    )
    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")

    # The page's cache signature includes the signed-in user id, which is
    # not observable from here. Every other component is fixed by the state
    # injected above, so the candidate ids are tried until the cache is
    # recognised — a guess that silently missed would make this test pass
    # for the wrong reason.
    values = []
    for candidate_uid in (None, 1, 0):
        at.session_state["_trades_summary"] = {
            "sig": (
                candidate_uid,
                "2026-06-01",
                "2026-06-30",
                (),
                "All",
                "All",
                "All",
                len(ids),
            ),
            "review": {"content_md": document},
        }
        at = at.run()
        if at.exception:
            return _fail(f"rendering the summary raised: {at.exception}")
        # Streamlit strips surrounding whitespace from a markdown element's
        # source, so compare stripped rather than byte-for-byte.
        values = [m.value for m in at.markdown]
        if any(v.strip() == document.strip() for v in values):
            break
    else:
        return _fail(
            "summary was never rendered as its own Markdown element "
            f"(no candidate uid matched; markdown count={len(values)})"
        )
    # The failure mode being guarded: the document escaped into one HTML
    # string, where its headings survive only as literal "###" characters.
    # Matched on the document's own text, not on "###" alone — the injected
    # stylesheet is itself a markdown element and contains that class name.
    for value in values:
        if "What worked" in value and "tl-readout" in value:
            return _fail("summary Markdown was escaped into a readout body")
        if "&lt;" in value and "What worked" in value:
            return _fail("summary Markdown was HTML-escaped")
    # The Evidence Rail still accompanies it.
    if not any("tl-evidence-rail" in v for v in values):
        return _fail("summary lost its Evidence Rail")
    print("OK")
    return 0


_SCENARIOS = {
    "row_to_detail_and_back": scenario_row_to_detail_and_back,
    "calendar_day_to_detail": scenario_calendar_day_to_detail,
    "summary_markdown": scenario_summary_markdown,
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
    ids = _seed()
    return _SCENARIOS[scenario](root, ids)


if __name__ == "__main__":
    sys.exit(main())

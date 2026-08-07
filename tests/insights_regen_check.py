"""Subprocess helper: does a FAILED Daily Debrief regeneration destroy the note?

Not collected by pytest (no `test_` prefix) — `test_insights_page.py` drives it,
for the isolation reason spelled out in `app_boot_check.py`: reloading
`src.tradelens` mid-suite creates a second copy of `ai_client` and breaks
`isinstance` checks bound at collection time in other files.

Source-position tests cannot answer this question. The plan's version compares
the offsets of `.pop(` and `_run_daily_debrief(` inside one function, which says
nothing about what a trader is left looking at. This clicks the real control
with the real generator raising, and reads the rendered page.

Usage:
    DATABASE_URL=sqlite:///<tmp> python insights_regen_check.py <root> <mode>

    mode = "fail"    regeneration raises DebriefError — the prior note must
                     still be on screen, with the reason beside it
    mode = "succeed" regeneration returns a new note — it must replace the old
    mode = "inflight" freezes the busy pass at the moment of the call, so the
                     appearance DURING regeneration can be asserted: prior note
                     still on screen, control disabled, progress announced

Exits 0 on success; nonzero with a message on failure.
"""

import sys

PRIOR = "PRIOR NOTE BODY MARKER"
FRESH = "FRESH NOTE BODY MARKER"
DAY = "2026-06-15"


def main() -> int:
    root, mode = sys.argv[1], sys.argv[2]
    sys.path.insert(0, root)

    try:
        import streamlit as st

        st.secrets._secrets = {}
    except Exception:  # noqa: BLE001
        pass

    from src.tradelens.db.init_db import init_db

    init_db()

    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    session = SessionLocal()
    session.add(
        Trade(
            trade_date=DAY,
            asset="NQ",
            direction="Long",
            result="Win",
            pnl=200.0,
            killzone="ny_am",
        )
    )
    session.commit()
    session.close()

    # Patch the SERVICE module's attribute, not the page's. The page does
    # `from ...debrief import generate_debrief` at module scope, and AppTest
    # executes the page script on every run — so the name is rebound from
    # this module each time, and patching here is what the page will see.
    from src.tradelens.services import debrief as debrief_service

    calls = {"n": 0}

    def _fail(*_a, **_k):
        calls["n"] += 1
        raise debrief_service.DebriefError("The day's trades could not be read.")

    def _succeed(*_a, **_k):
        calls["n"] += 1
        return (
            {"content_md": f"## Fresh\n{FRESH}", "stats": {"trades": 1}},
            {"input_tokens": 1, "output_tokens": 1},
        )

    def _freeze(*_a, **_k):
        """Halt the script exactly where the blocking call would sit.

        `st.stop()` ends the run at this point, so AppTest's final state is
        the busy pass itself — the one a browser shows for the whole duration
        of a real call. Without this the pass is invisible here: AppTest
        resolves the `st.rerun()` that follows inside the same `run()`.
        """
        calls["n"] += 1
        import streamlit as _st

        _st.stop()

    debrief_service.generate_debrief = {
        "fail": _fail,
        "succeed": _succeed,
        "inflight": _freeze,
    }[mode]

    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(f"{root}/src/tradelens/ui/pages/6_Insights.py")
    at.session_state["authenticated"] = True
    at.session_state["ai_review_lens"] = "Daily Debrief"
    at.session_state["ins_dbf_day"] = __import__("datetime").date(2026, 6, 15)
    at = at.run(timeout=120)
    if at.exception:
        print(f"app raised on first run: {at.exception}", file=sys.stderr)
        return 2

    # The cache key is built from the page's own uid; read it back rather than
    # guessing, so a change to how the page scopes its cache fails loudly here
    # instead of silently testing nothing.
    keys = [
        k
        for k in at.session_state.filtered_state
        if k.startswith("_dbf_") and k.endswith(DAY)
    ]
    if not keys:
        # No debrief has been generated yet, which is the expected start; seed
        # the prior note under the key the page will look for.
        uid = at.session_state.filtered_state.get("current_user_id")
        cache_key = f"_dbf_{uid}_{DAY}"
    else:
        cache_key = keys[0]

    at.session_state[cache_key] = {
        "content_md": f"## Prior\n{PRIOR}",
        "stats": {"trades": 1, "win_rate": 1.0, "total_pnl": 200.0},
    }
    at = at.run(timeout=120)
    if at.exception:
        print(f"app raised showing the prior note: {at.exception}", file=sys.stderr)
        return 3

    def rendered() -> str:
        return "\n".join(
            [m.value for m in at.markdown]
            + [c.value for c in at.caption]
            + [t.value for t in at.title]
        )

    if PRIOR not in rendered():
        print(f"prior note never rendered under {cache_key}", file=sys.stderr)
        return 4

    regen = [b for b in at.button if "Regenerate debrief" in (b.label or "")]
    if not regen:
        print("no regenerate control found", file=sys.stderr)
        return 5
    if regen[0].disabled:
        print(
            "regenerate control was already disabled before any click", file=sys.stderr
        )
        return 6

    if mode == "inflight":
        # Enter the busy pass directly. Clicking would only record intent and
        # rerun, and the rerun is resolved inside the same run() here.
        at.session_state[cache_key + "_busy"] = True
        at = at.run(timeout=120)
        if at.exception:
            print(f"app raised in flight: {at.exception}", file=sys.stderr)
            return 20
        page = rendered()
        if PRIOR not in page:
            print("prior note vanished while regenerating", file=sys.stderr)
            return 21
        if "Updating review" not in page:
            print("no polite inline progress while regenerating", file=sys.stderr)
            return 22
        live = [b for b in at.button if "Regenerate debrief" in (b.label or "")]
        if not live:
            print("regenerate control disappeared while in flight", file=sys.stderr)
            return 23
        if not live[0].disabled:
            print("regenerate control was still live during the call", file=sys.stderr)
            return 24
        if calls["n"] != 1:
            print(f"generator ran {calls['n']} times in flight", file=sys.stderr)
            return 25
        print("OK")
        return 0

    # Click, then let the two passes settle.
    #
    # Measured, not assumed: AppTest resolves `st.rerun()` INSIDE the same
    # `run()` call, so the click pass and the generation pass are not
    # separately observable here — after one `click().run()` the generator has
    # already run. That is a property of the harness, not of the page: in a
    # browser Streamlit streams each pass's deltas as they are produced, so
    # the disabled control and the progress line are on screen for the whole
    # blocking call. The in-flight appearance is therefore verified in the
    # browser instead, and this check owns the part a browser cannot force —
    # what survives a generator that raises.
    at = regen[0].click().run(timeout=120)
    if at.exception:
        print(f"app raised on regeneration: {at.exception}", file=sys.stderr)
        return 7
    if calls["n"] != 1:
        print(f"generator ran {calls['n']} times, expected exactly 1", file=sys.stderr)
        return 8

    page = rendered()
    if mode == "fail":
        if PRIOR not in page:
            print("FAILED REGENERATION DESTROYED THE PRIOR NOTE", file=sys.stderr)
            return 14
        if "could not be read" not in page:
            print("no trader-safe reason shown beside the kept note", file=sys.stderr)
            return 15
    else:
        if FRESH not in page:
            print("successful regeneration did not replace the note", file=sys.stderr)
            return 16
        if PRIOR in page:
            print("the replaced note is still on screen", file=sys.stderr)
            return 17

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

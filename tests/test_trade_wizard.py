"""
Tests for src/tradelens/ui/components/trade_wizard.py (premium redesign, Task 4).

The wizard's state machine is pure and Streamlit-free, so the rules that
decide what a trader can do next are testable without a browser:

- the step never leaves 1..5, whatever lands in session state;
- moving backward and forward never touches field values;
- only genuinely blocking fields are required, and reflection is never one
  of them — an optional field that blocks a save is a bug, not a guardrail;
- a reset clears wizard-owned keys and nothing else.
"""

import os
from pathlib import Path

import pytest

from src.tradelens.ui.components import trade_wizard as tw
from src.tradelens.ui.components.trade_wizard import (
    FIRST_STEP,
    LAST_STEP,
    WIZARD_STATE_KEY,
    WIZARD_STEPS,
    current_step,
    draft_completion,
    is_blank,
    missing_required_fields,
    next_step,
    previous_step,
    required_fields_for_step,
    reset_wizard_state,
    set_step,
    step_progress,
    wizard_owned_keys,
)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_the_wizard_has_the_five_approved_steps_in_order():
    assert WIZARD_STEPS == (
        "Screenshot",
        "Context",
        "Execution",
        "Reflection",
        "Review",
    )
    assert FIRST_STEP == 1
    assert LAST_STEP == 5


def test_module_is_streamlit_free():
    from pathlib import Path

    src = Path(tw.__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import streamlit", "from streamlit")):
            assert line != stripped, f"top-level streamlit import: {line!r}"


# ---------------------------------------------------------------------------
# current_step / set_step — clamping
# ---------------------------------------------------------------------------


def test_current_step_defaults_to_the_first_step():
    assert current_step({}) == 1


def test_current_step_clamps_out_of_range_values():
    assert current_step({WIZARD_STATE_KEY: 0}) == 1
    assert current_step({WIZARD_STATE_KEY: -7}) == 1
    assert current_step({WIZARD_STATE_KEY: 6}) == 5
    assert current_step({WIZARD_STATE_KEY: 99}) == 5


def test_current_step_survives_junk_in_session_state():
    """Session state is a dict anyone can write to; a render path that
    raises on junk takes the whole page down."""
    for junk in ("three", None, [], {}, object()):
        assert current_step({WIZARD_STATE_KEY: junk}) == 1


def test_current_step_accepts_a_numeric_string():
    assert current_step({WIZARD_STATE_KEY: "3"}) == 3


def test_set_step_clamps_and_writes():
    state = {}
    set_step(state, 3)
    assert state[WIZARD_STATE_KEY] == 3
    set_step(state, 99)
    assert state[WIZARD_STATE_KEY] == 5
    set_step(state, -1)
    assert state[WIZARD_STATE_KEY] == 1


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_next_and_previous_walk_the_steps():
    state = {}
    for expected in (2, 3, 4, 5):
        next_step(state)
        assert current_step(state) == expected
    for expected in (4, 3, 2, 1):
        previous_step(state)
        assert current_step(state) == expected


def test_navigation_stops_at_the_ends_instead_of_wrapping():
    state = {WIZARD_STATE_KEY: 5}
    next_step(state)
    assert current_step(state) == 5

    state = {WIZARD_STATE_KEY: 1}
    previous_step(state)
    assert current_step(state) == 1


def test_navigation_never_touches_field_values():
    """The draft is the point: stepping back to fix one field must not cost
    a trader the other twenty."""
    state = {
        WIZARD_STATE_KEY: 2,
        "nt_asset": "NQ",
        "nt_pnl": 250.0,
        "nt_mindset": "calm",
    }
    next_step(state)
    previous_step(state)
    previous_step(state)
    assert state["nt_asset"] == "NQ"
    assert state["nt_pnl"] == 250.0
    assert state["nt_mindset"] == "calm"


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


def test_step_progress_spans_the_wizard():
    assert step_progress(1) == pytest.approx(0.2)
    assert step_progress(5) == pytest.approx(1.0)
    assert 0.0 < step_progress(3) < 1.0


def test_step_progress_clamps():
    assert step_progress(0) == pytest.approx(0.2)
    assert step_progress(99) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Required fields — reflection is never required
# ---------------------------------------------------------------------------


def test_only_context_blocks_progress():
    """Asset and entry time are the two fields a trade cannot be recorded
    without. Everything else is a recommendation."""
    assert required_fields_for_step(1) == ()
    assert set(required_fields_for_step(2)) == {"asset", "entry_time"}
    assert required_fields_for_step(3) == ()
    assert required_fields_for_step(4) == ()
    assert required_fields_for_step(5) == ()


def test_reflection_fields_are_never_required():
    """An optional field that blocks the save is the single fastest way to
    stop a trader journalling."""
    for step in range(FIRST_STEP, LAST_STEP + 1):
        required = set(required_fields_for_step(step))
        for optional in (
            "mindset",
            "did_well",
            "do_better",
            "process_notes",
            "mistake_tags",
            "screenshot",
            "confirmation_model",
        ):
            assert optional not in required


def test_missing_required_fields_reports_human_labels():
    missing = missing_required_fields(2, {"asset": "", "entry_time": None})
    assert missing == ["Asset", "Entry time"]


def test_missing_required_fields_is_empty_when_satisfied():
    assert missing_required_fields(2, {"asset": "NQ", "entry_time": "09:30"}) == []


def test_missing_required_fields_treats_whitespace_as_blank():
    assert missing_required_fields(2, {"asset": "   ", "entry_time": "09:30"}) == [
        "Asset"
    ]


def test_steps_without_requirements_never_report_anything_missing():
    for step in (1, 3, 4, 5):
        assert missing_required_fields(step, {}) == []


# ---------------------------------------------------------------------------
# is_blank
# ---------------------------------------------------------------------------


def test_is_blank_covers_the_shapes_a_widget_can_return():
    for blank in (None, "", "   ", [], (), {}):
        assert is_blank(blank), blank
    for filled in ("NQ", 0, 0.0, ["FVG"], False):
        assert not is_blank(filled), filled


def test_zero_is_not_blank():
    """A P&L of exactly 0.00 is a breakeven trade, not a missing value."""
    assert not is_blank(0)
    assert not is_blank(0.0)


# ---------------------------------------------------------------------------
# Draft completion
# ---------------------------------------------------------------------------


def test_draft_completion_counts_filled_tracked_fields():
    filled, total = draft_completion({})
    assert filled == 0
    assert total > 0

    filled, total = draft_completion({"asset": "NQ", "pnl": 100.0})
    assert filled == 2


def test_draft_completion_ignores_untracked_keys():
    filled, _ = draft_completion({"something_else": "x", "asset": "NQ"})
    assert filled == 1


def test_draft_completion_never_exceeds_its_total():
    everything = {key: "x" for key in tw.TRACKED_FIELDS}
    filled, total = draft_completion(everything)
    assert filled == total


# ---------------------------------------------------------------------------
# Reset — wizard-owned keys only
# ---------------------------------------------------------------------------


def test_wizard_owned_keys_are_the_nt_prefix_and_the_step():
    state = {
        "nt_asset": "NQ",
        "nt_pnl": 1.0,
        WIZARD_STATE_KEY: 3,
        "authenticated": True,
        "current_user": "ayoub",
        "dash_asset": "All assets",
    }
    owned = set(wizard_owned_keys(state))
    assert owned == {"nt_asset", "nt_pnl", WIZARD_STATE_KEY}


def test_reset_clears_only_wizard_keys():
    """A reset that takes the session with it signs the trader out at the
    moment they finish their first trade."""
    state = {
        "nt_asset": "NQ",
        "nt_pnl": 1.0,
        WIZARD_STATE_KEY: 4,
        "authenticated": True,
        "current_user": "ayoub",
        "just_saved_trade_id": 12,
    }
    reset_wizard_state(state)
    assert "nt_asset" not in state
    assert "nt_pnl" not in state
    assert state["authenticated"] is True
    assert state["current_user"] == "ayoub"
    assert state["just_saved_trade_id"] == 12


def test_keep_alive_preserves_values_without_changing_them():
    """Streamlit discards a widget's state on any run where the widget is
    not rendered. A one-step-at-a-time wizard would therefore lose every
    field outside the active step; re-asserting the key prevents that."""
    state = {
        "nt_asset": "NQ",
        "nt_pnl": 0.0,
        "nt_confluences": ["FVG"],
        WIZARD_STATE_KEY: 3,
        "authenticated": True,
    }
    before = dict(state)
    tw.keep_alive(state)
    assert state == before


def test_keep_alive_touches_only_wizard_keys():
    seen = []

    class _Recorder(dict):
        def __setitem__(self, key, value):
            seen.append(key)
            super().__setitem__(key, value)

    state = _Recorder({"nt_asset": "NQ", "authenticated": True, WIZARD_STATE_KEY: 2})
    tw.keep_alive(state)
    assert set(seen) == {"nt_asset", WIZARD_STATE_KEY}


def test_reset_returns_the_wizard_to_step_one():
    state = {WIZARD_STATE_KEY: 5, "nt_asset": "NQ"}
    reset_wizard_state(state)
    assert current_step(state) == 1


# ---------------------------------------------------------------------------
# AppTest — the wizard as a trader actually drives it.
#
# In-process is safe here: AppTest executes the page script in a fresh module
# namespace but reuses already-imported src.tradelens modules from sys.modules.
# The suite-corrupting trap documented in app_boot_check.py is PURGING
# sys.modules and re-importing, which none of these do. No scenario saves, so
# no test touches the database.
# ---------------------------------------------------------------------------

_PAGE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "tradelens"
    / "ui"
    / "pages"
    / "1_NewTrade.py"
)


def _wizard(**state):
    from streamlit.testing.v1 import AppTest

    os.environ.setdefault("DEMO_MODE", "true")
    at = AppTest.from_file(str(_PAGE), default_timeout=60)
    at.session_state["authenticated"] = True
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def _labels(at):
    return [b.label for b in at.button]


def test_wizard_opens_on_step_one_with_no_save_button():
    at = _wizard()
    assert not at.exception
    assert at.session_state[WIZARD_STATE_KEY] == 1
    assert "Continue →" in _labels(at)
    assert "Save completed trade" not in _labels(at)
    assert "← Back" not in _labels(at), "nowhere to go back to from step one"


def test_continue_advances_and_back_returns():
    at = _wizard()
    cont = next(b for b in at.button if b.label == "Continue →")
    cont.click().run()
    assert at.session_state[WIZARD_STATE_KEY] == 2
    assert "← Back" in _labels(at)

    back = next(b for b in at.button if b.label == "← Back")
    back.click().run()
    assert at.session_state[WIZARD_STATE_KEY] == 1


def test_entered_values_survive_moving_between_steps():
    """The whole point of a draft: correcting one field must not cost the
    other twenty."""
    at = _wizard(
        new_trade_step=3,
        nt_asset_select="NQ",
        nt_pnl=250.0,
        nt_mindset="patient",
        nt_confluences=["FVG"],
    )
    back = next(b for b in at.button if b.label == "← Back")
    back.click().run()
    assert at.session_state[WIZARD_STATE_KEY] == 2

    cont = next(b for b in at.button if b.label == "Continue →")
    cont.click().run()
    assert at.session_state[WIZARD_STATE_KEY] == 3
    assert at.session_state["nt_asset_select"] == "NQ"
    assert at.session_state["nt_pnl"] == 250.0
    assert at.session_state["nt_mindset"] == "patient"
    assert at.session_state["nt_confluences"] == ["FVG"]


def test_blank_required_field_blocks_continue_and_says_why():
    """Asset is blank only when the trader picks Other and types nothing."""
    from src.tradelens.services.assets import OTHER

    at = _wizard(new_trade_step=2, nt_asset_select=OTHER, nt_asset_custom="")
    cont = next(b for b in at.button if b.label == "Continue →")
    cont.click().run()

    assert at.session_state[WIZARD_STATE_KEY] == 2, "must not advance"
    assert at.session_state["_nt_step_errors"] == ["Asset"]
    assert any("Asset" in m.value for m in at.markdown)


def test_filling_the_required_field_unblocks_continue():
    from src.tradelens.services.assets import OTHER

    at = _wizard(new_trade_step=2, nt_asset_select=OTHER, nt_asset_custom="MNQ")
    cont = next(b for b in at.button if b.label == "Continue →")
    cont.click().run()
    assert at.session_state[WIZARD_STATE_KEY] == 3


def test_unreadable_entry_time_blocks_continue():
    at = _wizard(new_trade_step=2, nt_entry_time="not a time")
    cont = next(b for b in at.button if b.label == "Continue →")
    cont.click().run()
    assert at.session_state[WIZARD_STATE_KEY] == 2
    assert at.session_state["_nt_step_errors"] == ["Entry time"]


def test_review_saves_with_every_reflection_field_blank():
    """Optional means optional: a blank Reflection step must leave the save
    action live."""
    at = _wizard(
        new_trade_step=5,
        nt_asset_select="NQ",
        nt_entry_time="09:30",
        nt_process_notes="",
        nt_mindset="",
        nt_did_well="",
        nt_do_better="",
    )
    assert not at.exception
    save = next(b for b in at.button if b.label == "Save completed trade")
    assert not save.disabled, "reflection is optional and must not block saving"


def test_review_disables_save_while_a_blocking_error_stands():
    from src.tradelens.services.assets import OTHER

    at = _wizard(new_trade_step=5, nt_asset_select=OTHER, nt_asset_custom="")
    save = next(b for b in at.button if b.label == "Save completed trade")
    assert save.disabled
    assert any("Asset is required" in m.value for m in at.markdown)


def test_only_the_active_step_renders():
    """Step 1's uploader and step 3's setup picker must never coexist."""
    at_one = _wizard(new_trade_step=1)
    assert len(at_one.get("file_uploader")) == 1

    at_three = _wizard(new_trade_step=3)
    assert len(at_three.get("file_uploader")) == 0
    assert any(s.label == "Setup model" for s in at_three.selectbox)


def test_every_step_boots_without_raising():
    for step in range(1, 6):
        at = _wizard(new_trade_step=step)
        assert not at.exception, f"step {step} raised: {at.exception}"

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
import re
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


def test_wizard_owned_keys_include_private_ai_and_submit_state_but_not_owner():
    state = {
        "nt_asset": "NQ",
        "_nt_ai_result": {"asset": "NQ"},
        "_nt_step_errors": ["Asset"],
        "trade_submit_in_progress": True,
        "just_saved_trade_id": 42,
        tw.WIZARD_OWNER_KEY: "id:7",
        "authenticated": True,
    }
    assert set(wizard_owned_keys(state)) == {
        "nt_asset",
        "_nt_ai_result",
        "_nt_step_errors",
        "trade_submit_in_progress",
        "just_saved_trade_id",
    }


def test_reset_clears_only_wizard_keys():
    """A reset that takes the session with it signs the trader out at the
    moment they finish their first trade."""
    state = {
        "nt_asset": "NQ",
        "nt_pnl": 1.0,
        WIZARD_STATE_KEY: 4,
        "authenticated": True,
        "current_user": "ayoub",
        "_nt_ai_result": {"asset": "NQ"},
        "just_saved_trade_id": 12,
        tw.WIZARD_OWNER_KEY: "id:7",
    }
    reset_wizard_state(state)
    assert "nt_asset" not in state
    assert "nt_pnl" not in state
    assert state["authenticated"] is True
    assert state["current_user"] == "ayoub"
    assert "_nt_ai_result" not in state
    assert "just_saved_trade_id" not in state
    assert state[tw.WIZARD_OWNER_KEY] == "id:7"


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


def test_same_owner_keeps_the_entire_draft():
    state = {
        tw.WIZARD_OWNER_KEY: "id:7",
        WIZARD_STATE_KEY: 4,
        "nt_asset": "NQ",
        "_nt_ai_result": {"asset": "NQ"},
        "authenticated": True,
    }
    before = dict(state)
    assert tw.scope_wizard_to_owner(state, "id:7") is False
    assert state == before


def test_account_change_clears_draft_and_private_ai_state():
    """Session state survives navigation and sign-out. A draft owned by one
    trader must never become visible or saveable after another trader signs in."""
    state = {
        tw.WIZARD_OWNER_KEY: "id:7",
        WIZARD_STATE_KEY: 4,
        "nt_asset": "NQ",
        "nt_process_notes": "private journal note",
        "_nt_ai_result": {"summary": "private model output"},
        "trade_submit_in_progress": True,
        "just_saved_trade_id": 42,
        "authenticated": True,
        "current_user": "second-user",
    }
    assert tw.scope_wizard_to_owner(state, "id:9") is True
    assert state[tw.WIZARD_OWNER_KEY] == "id:9"
    assert current_step(state) == FIRST_STEP
    for private_key in (
        "nt_asset",
        "nt_process_notes",
        "_nt_ai_result",
        "trade_submit_in_progress",
        "just_saved_trade_id",
    ):
        assert private_key not in state
    assert state["authenticated"] is True
    assert state["current_user"] == "second-user"


def test_unowned_legacy_draft_is_cleared_before_being_claimed():
    """After this boundary is introduced, an existing unscoped draft has no
    trustworthy owner. Clearing it once is safer than assigning it to whoever
    happens to sign in next."""
    state = {
        WIZARD_STATE_KEY: 3,
        "nt_asset": "ES",
        "_nt_ai_result": {"asset": "ES"},
    }
    assert tw.scope_wizard_to_owner(state, "user:ayoub") is True
    assert state == {
        tw.WIZARD_OWNER_KEY: "user:ayoub",
        WIZARD_STATE_KEY: FIRST_STEP,
    }


def test_save_failure_copy_never_exposes_exception_details():
    secret = "postgresql://user:password@private-host/tradelens"
    message = tw.safe_save_failure_message(RuntimeError(secret))
    assert secret not in message
    assert "RuntimeError" not in message
    assert "try again" in message.lower()


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
    at.session_state["current_user"] = "test-trader"
    at.session_state[tw.WIZARD_OWNER_KEY] = "user:test-trader"
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
    assert any("Enter a custom asset" in c.value for c in at.caption)


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


def test_blank_entry_time_gets_recovery_copy_beside_the_field():
    at = _wizard(new_trade_step=2, nt_entry_time="")
    cont = next(b for b in at.button if b.label == "Continue →")
    cont.click().run()
    assert at.session_state["_nt_step_errors"] == ["Entry time"]
    assert any("Enter a trade time" in c.value for c in at.caption)


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


# ---------------------------------------------------------------------------
# Back navigation and the file-uploader key
# ---------------------------------------------------------------------------
# Streamlit refuses `st.session_state[key] = ...` for widgets whose value only
# the user can supply — file_uploader among them. keep_alive re-asserts every
# wizard key so a one-step-at-a-time wizard does not lose off-step values, and
# that generic sweep collided with `nt_shot`: the assignment marked the key
# user-set, and re-instantiating the uploader on the way back raised
# StreamlitValueAssignmentNotAllowedError. No upload is needed to reproduce it
# — instantiating the uploader once puts `nt_shot` in session state.


def test_keep_alive_skips_keys_streamlit_forbids_assigning():
    """`nt_shot` must survive keep_alive without being re-assigned."""
    seen = []

    class _Recorder(dict):
        def __setitem__(self, key, value):
            seen.append(key)
            super().__setitem__(key, value)

    state = _Recorder({"nt_asset": "NQ", "nt_shot": None, WIZARD_STATE_KEY: 2})
    tw.keep_alive(state)

    assert "nt_shot" not in seen, "assigning a file_uploader key raises in Streamlit"
    assert "nt_asset" in seen, "ordinary wizard keys must still be re-asserted"
    assert "nt_shot" in state, "the key must be left in place, only not re-assigned"


class _Shot:
    """Stand-in for an UploadedFile: identity and name are all that matter."""

    def __init__(self, name="chart.png"):
        self.name = name


def test_mirror_stores_the_upload_on_a_change_event():
    shot = _Shot()
    state = {tw.SCREENSHOT_WIDGET_KEY: shot}
    tw.sync_screenshot_mirror(state)
    assert state[tw.SCREENSHOT_DRAFT_KEY] is shot


def test_mirror_clears_on_a_genuine_removal():
    """The trader clicked the uploader's ✕, so the widget reports None on a
    real change event. That is a removal and must drop the mirror."""
    state = {tw.SCREENSHOT_WIDGET_KEY: None, tw.SCREENSHOT_DRAFT_KEY: _Shot()}
    tw.sync_screenshot_mirror(state)
    assert tw.SCREENSHOT_DRAFT_KEY not in state


def test_mirror_replaces_on_a_second_upload():
    first, second = _Shot("first.png"), _Shot("second.png")
    state = {tw.SCREENSHOT_WIDGET_KEY: first}
    tw.sync_screenshot_mirror(state)
    state[tw.SCREENSHOT_WIDGET_KEY] = second
    tw.sync_screenshot_mirror(state)
    assert state[tw.SCREENSHOT_DRAFT_KEY] is second


def test_a_remount_does_not_touch_the_mirror():
    """The regression Codex caught.

    After Back the uploader remounts empty and reports None *without* firing
    its change callback. Nothing may run sync_screenshot_mirror on that path,
    so the mirror — and the draft field count — must survive untouched.
    """
    shot = _Shot()
    state = {tw.SCREENSHOT_WIDGET_KEY: None, tw.SCREENSHOT_DRAFT_KEY: shot}

    # A render is not a change: only effective_screenshot runs on this path.
    assert tw.effective_screenshot(state) is shot
    assert state[tw.SCREENSHOT_DRAFT_KEY] is shot


def test_effective_screenshot_prefers_the_live_widget():
    live, mirrored = _Shot("live.png"), _Shot("mirrored.png")
    assert (
        tw.effective_screenshot(
            {tw.SCREENSHOT_WIDGET_KEY: live, tw.SCREENSHOT_DRAFT_KEY: mirrored}
        )
        is live
    )


def test_effective_screenshot_falls_back_to_the_mirror():
    mirrored = _Shot()
    assert (
        tw.effective_screenshot(
            {tw.SCREENSHOT_WIDGET_KEY: None, tw.SCREENSHOT_DRAFT_KEY: mirrored}
        )
        is mirrored
    )


def test_effective_screenshot_is_none_when_nothing_is_held():
    assert tw.effective_screenshot({}) is None
    assert tw.effective_screenshot({tw.SCREENSHOT_WIDGET_KEY: None}) is None


def test_the_page_syncs_the_mirror_only_from_the_change_callback():
    """Structural guard for the defect Codex caught.

    A render-time `pop(SCREENSHOT_DRAFT_KEY)` deletes the chart every time the
    uploader remounts. The mirror may only be cleared from the change callback
    or the explicit remove control.
    """
    source = _PAGE.read_text(encoding="utf-8")

    uploader = re.search(r"st\.file_uploader\((.*?)\n    \)", source, flags=re.DOTALL)
    assert uploader, "could not locate the file_uploader call"
    assert "on_change=" in uploader.group(
        1
    ), "the uploader must synchronise its mirror through on_change"

    body = source[source.index("def _step_screenshot()") :]
    body = body[: body.index("\ndef ")]
    pops = re.findall(r"pop\(\s*SCREENSHOT_DRAFT_KEY", body)
    assert len(pops) <= 1, (
        "the only mirror deletion inside _step_screenshot may be the explicit "
        f"Remove control; found {len(pops)}"
    )


def test_ownership_change_clears_the_mirror():
    """A different trader must never inherit the previous one's chart."""
    state = {tw.SCREENSHOT_DRAFT_KEY: _Shot(), tw.WIZARD_OWNER_KEY: "id:1"}
    tw.scope_wizard_to_owner(state, "id:2")
    assert tw.SCREENSHOT_DRAFT_KEY not in state


def test_screenshot_draft_key_is_wizard_owned():
    """The mirror that carries the upload across steps must reset with the
    wizard. A mirror outside the owned prefix would survive a reset and leak
    one trader's chart into the next draft."""
    state = {tw.SCREENSHOT_DRAFT_KEY: object(), WIZARD_STATE_KEY: 3}
    assert tw.SCREENSHOT_DRAFT_KEY in wizard_owned_keys(state)

    reset_wizard_state(state)
    assert tw.SCREENSHOT_DRAFT_KEY not in state


_AUTOFILL = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "tradelens"
    / "ui"
    / "components"
    / "ai_autofill_review.py"
)

# Widget types whose value Streamlit refuses to accept from session_state.
_UNSETTABLE_WIDGETS = (
    "button",
    "download_button",
    "form_submit_button",
    "chat_input",
    "file_uploader",
)


def _declared_unsettable_keys(source: str) -> set:
    """Every wizard-prefixed key the source gives an unsettable widget."""
    keys = set()
    for widget in _UNSETTABLE_WIDGETS:
        for call in re.findall(
            rf"\.{widget}\((.*?)\n\s*\)|\.{widget}\(([^()]*)\)",
            source,
            flags=re.DOTALL,
        ):
            body = call[0] or call[1]
            literal = re.search(r"""key\s*=\s*["']([^"']+)["']""", body)
            if literal:
                keys.add(literal.group(1))
                continue
            named = re.search(r"key\s*=\s*([A-Z_][A-Z0-9_]*)\s*[,)]", body)
            if named:
                resolved = getattr(tw, named.group(1), None)
                assert isinstance(resolved, str), (
                    f"{widget} key {named.group(1)!r} does not resolve to a "
                    "string constant on trade_wizard; this guard cannot verify it"
                )
                keys.add(resolved)
    return {
        k
        for k in keys
        if k.startswith(tw.FIELD_PREFIX) or k.startswith(tw.PRIVATE_PREFIX)
    }


def test_every_unsettable_widget_key_is_exempt_from_keep_alive():
    """The real guard against this class of regression returning.

    Any uploader or button the wizard renders under its own key prefixes will
    be swept up by keep_alive and crash Back navigation. The first fix covered
    only `nt_shot`; a real-file browser run then hit `_nt_ai_analyze`, a button
    in the autofill panel that only appears once a chart has been uploaded.
    So bind the exemption set to the source of both files rather than to a
    remembered list.
    """
    declared = _declared_unsettable_keys(
        _PAGE.read_text(encoding="utf-8")
    ) | _declared_unsettable_keys(_AUTOFILL.read_text(encoding="utf-8"))

    assert declared, "expected to find unsettable widget keys to check"

    missing = declared - tw.UNSETTABLE_WIDGET_KEYS
    assert not missing, (
        f"unsettable widget key(s) {sorted(missing)} are not in "
        "UNSETTABLE_WIDGET_KEYS; keep_alive will assign them and Back "
        "navigation will raise StreamlitValueAssignmentNotAllowedError"
    )


def test_the_exemption_set_has_no_dead_entries():
    """An exemption for a key nothing declares is a stale note, and it hides
    the fact that the widget it named is gone."""
    declared = _declared_unsettable_keys(
        _PAGE.read_text(encoding="utf-8")
    ) | _declared_unsettable_keys(_AUTOFILL.read_text(encoding="utf-8"))

    stale = tw.UNSETTABLE_WIDGET_KEYS - declared
    assert not stale, f"UNSETTABLE_WIDGET_KEYS lists absent widgets: {sorted(stale)}"


# The two round trips below are workflow smoke tests, NOT regressions guards
# for this defect. AppTest discards `nt_shot` at the end of the step-2 run, so
# the user-set marking that makes the real runtime raise never survives to the
# Back run — verified: these pass against the unfixed code. The browser
# round trip in the preflight audit is what proves the fix; the unit tests
# above are what keep it fixed.


def test_step_one_to_two_and_back_does_not_raise():
    """Workflow smoke test for step 1 → Continue → Back.

    Companion to docs/superpowers/audits/2026-08-03-browser-preflight.md.
    """
    at = _wizard(new_trade_step=1)
    assert not at.exception, f"step 1 raised on entry: {at.exception}"
    assert len(at.get("file_uploader")) == 1, "the uploader must render on step 1"

    next(b for b in at.button if b.label == "Continue →").click().run()
    assert not at.exception, f"Continue raised: {at.exception}"
    assert at.session_state[WIZARD_STATE_KEY] == 2

    next(b for b in at.button if b.label == "← Back").click().run()
    assert not at.exception, f"Back raised: {at.exception}"
    assert at.session_state[WIZARD_STATE_KEY] == 1
    assert len(at.get("file_uploader")) == 1, "step 1 must render its uploader again"


def test_back_and_forward_across_every_step_does_not_raise():
    """Walking the whole wizard forward and back exercises the uploader key on
    every transition, not only the first."""
    at = _wizard(new_trade_step=1)
    for expected in range(2, LAST_STEP + 1):
        next(b for b in at.button if b.label == "Continue →").click().run()
        assert not at.exception, f"Continue into step {expected} raised: {at.exception}"
        assert at.session_state[WIZARD_STATE_KEY] == expected

    for expected in range(LAST_STEP - 1, 0, -1):
        next(b for b in at.button if b.label == "← Back").click().run()
        assert not at.exception, f"Back into step {expected} raised: {at.exception}"
        assert at.session_state[WIZARD_STATE_KEY] == expected

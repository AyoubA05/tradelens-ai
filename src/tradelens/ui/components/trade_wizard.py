"""State machine for the five-step Log-a-trade wizard.

Pure and Streamlit-free: these functions decide what step a trader is on,
what still blocks them, and how much of the draft is filled — none of which
needs a browser to be correct, and all of which is easier to trust when it
can be tested directly.

Two rules shape everything here:

**The draft is sacred.** Navigation only ever moves a step counter. Field
values live in session state under their own keys and are never touched by
moving between steps, so stepping back to correct one field cannot cost a
trader the other twenty.

**Only genuinely blocking fields are required.** A trade cannot be recorded
without an asset and a readable entry time, so those two block. Reflection —
what happened, how it felt, what to do better — is the part of journalling
people skip when it fights them, so it never blocks a save.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping

WIZARD_STEPS: tuple[str, ...] = (
    "Screenshot",
    "Context",
    "Execution",
    "Reflection",
    "Review",
)
WIZARD_STATE_KEY = "new_trade_step"
WIZARD_OWNER_KEY = "_nt_wizard_owner"

FIRST_STEP = 1
LAST_STEP = len(WIZARD_STEPS)

# Prefix every wizard-owned field key carries. A reset walks this prefix, so
# nothing outside the wizard (auth, demo flags, other pages' widgets) can be
# cleared by finishing a trade.
FIELD_PREFIX = "nt_"
PRIVATE_PREFIX = "_nt_"
_AUXILIARY_KEYS = frozenset({"trade_submit_in_progress", "just_saved_trade_id"})

# (field, label) pairs that block moving on, by step. Kept deliberately
# short: each entry is a field a trade is not a trade without.
_REQUIRED: dict[int, tuple[tuple[str, str], ...]] = {
    1: (),
    2: (("asset", "Asset"), ("entry_time", "Entry time")),
    3: (),
    4: (),
    5: (),
}

# What "how complete is this draft" counts. Not a validation list — a
# progress signal, so it includes the optional fields a good journal entry
# has, which is exactly what makes the count worth showing.
TRACKED_FIELDS: tuple[str, ...] = (
    "screenshot",
    "asset",
    "entry_time",
    "timeframe",
    "setup_type",
    "confluences",
    "followed_rules",
    "result",
    "pnl",
    "risk_amount",
    "position_size",
    "process_notes",
    "mindset",
    "did_well",
    "do_better",
)


def is_blank(value: object) -> bool:
    """True when a widget value carries nothing.

    Zero is NOT blank: a P&L of exactly 0.00 is a breakeven trade, and
    treating it as missing would nag a trader for the one number they were
    most careful about.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _clamp(step: int) -> int:
    return max(FIRST_STEP, min(LAST_STEP, step))


def current_step(state: Mapping[str, object]) -> int:
    """The active step, always within range.

    Session state is a dict anything can write to, so junk resolves to the
    first step rather than raising — this runs inside a render path, where
    an exception blanks the page.
    """
    raw = state.get(WIZARD_STATE_KEY, FIRST_STEP)
    try:
        return _clamp(int(raw))
    except (TypeError, ValueError):
        return FIRST_STEP


def set_step(state: MutableMapping[str, object], step: int) -> None:
    state[WIZARD_STATE_KEY] = _clamp(int(step))


def next_step(state: MutableMapping[str, object]) -> None:
    set_step(state, current_step(state) + 1)


def previous_step(state: MutableMapping[str, object]) -> None:
    set_step(state, current_step(state) - 1)


def step_progress(step: int) -> float:
    """How far through the wizard a step sits, as a 0-1 fraction."""
    return _clamp(int(step)) / LAST_STEP


def step_label(step: int) -> str:
    return WIZARD_STEPS[_clamp(int(step)) - 1]


def required_fields_for_step(step: int) -> tuple[str, ...]:
    return tuple(field for field, _label in _REQUIRED.get(_clamp(int(step)), ()))


def missing_required_fields(step: int, values: Mapping[str, object]) -> list[str]:
    """Human labels for the blocking fields still empty on this step.

    Labels, not keys: the caller writes the sentence, this decides what goes
    in it.
    """
    return [
        label
        for field, label in _REQUIRED.get(_clamp(int(step)), ())
        if is_blank(values.get(field))
    ]


def draft_completion(values: Mapping[str, object]) -> tuple[int, int]:
    """(filled, total) across the tracked fields — the draft-state signal."""
    filled = sum(1 for field in TRACKED_FIELDS if not is_blank(values.get(field)))
    return filled, len(TRACKED_FIELDS)


def wizard_owned_keys(state: Iterable[str]) -> list[str]:
    """Every session key this wizard is allowed to clear."""
    return [
        key
        for key in list(state)
        if (
            str(key).startswith(FIELD_PREFIX)
            or (str(key).startswith(PRIVATE_PREFIX) and key != WIZARD_OWNER_KEY)
            or key == WIZARD_STATE_KEY
            or key in _AUXILIARY_KEYS
        )
    ]


def scope_wizard_to_owner(state: MutableMapping[str, object], owner: str) -> bool:
    """Bind a draft to one authenticated identity.

    Streamlit session state survives page navigation and can survive the
    sign-out/sign-in path in the same browser tab. If the authenticated
    identity changes, every draft field and staged AI result is cleared
    before widgets render. An older unowned draft is also cleared once:
    there is no safe way to infer who created it.

    Returns ``True`` when an ownership boundary was crossed.
    """
    normalized_owner = str(owner)
    if state.get(WIZARD_OWNER_KEY) == normalized_owner:
        return False

    for key in wizard_owned_keys(state):
        state.pop(key, None)
    state[WIZARD_OWNER_KEY] = normalized_owner
    set_step(state, FIRST_STEP)
    return True


def safe_save_failure_message(_error: BaseException) -> str:
    """User-facing save failure copy with no exception or infrastructure data."""
    return "Could not save this trade. Please review your inputs and try again."


def keep_alive(state: MutableMapping[str, object]) -> None:
    """Re-assert every wizard value so Streamlit does not discard it.

    Streamlit drops a widget's session-state entry on any run where that
    widget is not rendered. A wizard renders one step at a time, so without
    this the moment a trader moved from Context to Execution their asset and
    entry time would silently vanish — and the save payload would rebuild
    from defaults. Re-assigning a key marks it user-set and keeps it.

    Must run at the top of the page, before any widget is instantiated.
    """
    for key in wizard_owned_keys(state):
        state[key] = state[key]


def reset_wizard_state(state: MutableMapping[str, object]) -> None:
    """Clear the wizard's own keys and return to step one.

    Scoped on purpose. A reset that takes the whole session with it signs
    the trader out at the exact moment they finish their first trade.
    """
    for key in wizard_owned_keys(state):
        state.pop(key, None)
    set_step(state, FIRST_STEP)

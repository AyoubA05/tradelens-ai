"""
AI Autofill Review panel (Session F, Phase 2).

The screenshot-first New Trade experience: the trader adds a chart, AI reviews it
post-trade, and the suggestions land in an editable review panel. Nothing is
applied automatically and nothing is written to the DB here — the panel only
stages suggestions into nt_* session-state so the normal form (and Save) stay in
control.

Layering:
  * build_form_writes / run_autofill are pure (no Streamlit) and unit-tested.
  * render_* helpers import Streamlit lazily (services/components stay importable
    without a Streamlit runtime, matching screenshot_analyzer.py).

Reuses, unchanged:
  * services/ai_screenshot_service.analyze_source — local path OR direct image URL
    (SSRF-hardened); we never fetch a URL ourselves.
  * services/ai_autofill.map_analysis_to_form — vision dict -> editable fields.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from src.tradelens.services.ai_autofill import AutofillResult, map_analysis_to_form
from src.tradelens.services.ai_screenshot_service import analyze_source
from src.tradelens.services.assets import OTHER, normalize_symbol
from src.tradelens.services.vision import ScreenshotAnalysisError

# Editable suggestion fields, in display order, mapped to their nt_* widget keys.
# "asset" is handled separately (it may route to the custom-asset text field).
_SIMPLE_FIELD_TO_KEY = {
    "timeframe": "nt_timeframe",
    "htf_bias": "nt_htf",
    "ltf_bias": "nt_ltf",
    "confluences": "nt_confluences",
}
_FIELD_LABELS = {
    "asset": "Asset",
    "timeframe": "Timeframe",
    "htf_bias": "HTF Bias",
    "ltf_bias": "LTF Bias",
    "confluences": "Confluences",
}
_FIELD_ORDER = ("asset", "timeframe", "htf_bias", "ltf_bias", "confluences")

# Session-state keys owned by this panel (cleared together between trades).
_RESULT_KEY = "_nt_ai_result"
_ANALYSIS_KEY = "_nt_ai_analysis"
_USAGE_KEY = "_nt_ai_usage"
_FIELDS_KEY = "_nt_ai_fields"  # set[str] of AI-sourced semantic fields (for badges)
_APPLIED_KEY = "_nt_ai_applied"  # list[str] applied on the last Apply (transient)
# Public: nt_* writes staged by Apply, drained by the page before widgets render.
PENDING_WRITES_KEY = "_nt_pending_writes"


# ---------------------------------------------------------------------------
# Pure logic (no Streamlit)
# ---------------------------------------------------------------------------


def build_form_writes(
    field_values: dict,
    selected: Iterable[str],
    known_assets: Optional[Iterable[str]] = None,
) -> dict:
    """Map accepted AI suggestions to a {nt_key: value} dict for session-state.

    Only ``selected`` fields with a usable value are written, so a suggestion can
    never blank out a form field. The asset is routed to the dropdown when it
    matches a known option, else to the custom-asset text field — and the
    dropdown write is always an *exact* option string (a normalized match still
    writes the real option, never a value the selectbox can't render).
    """
    selected = set(selected)
    writes: dict = {}

    if "asset" in selected:
        raw = field_values.get("asset")
        asset = normalize_symbol(raw) if isinstance(raw, str) else ""
        if asset:
            # First option per normalized symbol, so we write a real option string.
            known_map: dict = {}
            for option in known_assets or []:
                known_map.setdefault(normalize_symbol(option), option)
            if asset in known_map:
                writes["nt_asset_select"] = known_map[asset]
            else:
                writes["nt_asset_select"] = OTHER
                writes["nt_asset_custom"] = asset

    for field, key in _SIMPLE_FIELD_TO_KEY.items():
        if field in selected and field_values.get(field) is not None:
            writes[key] = field_values[field]

    return writes


def run_autofill(
    source,
    strategy_profile: Optional[dict],
    known_assets: Optional[Iterable[str]] = None,
) -> tuple[AutofillResult, dict, object]:
    """Analyze a screenshot source and map it to editable form suggestions.

    ``source`` is a local image path or a direct image URL. Returns
    (autofill_result, raw_analysis, usage): the result drives the review panel,
    the raw analysis + usage are persisted to AIAnalysis after the trade saves.
    Raises ScreenshotAnalysisError for an unreadable source.
    """
    analysis, usage = analyze_source(source, {}, strategy_profile)
    result = map_analysis_to_form(analysis, known_assets=known_assets)
    return result, analysis, usage


# ---------------------------------------------------------------------------
# Session-state helpers (Streamlit)
# ---------------------------------------------------------------------------


def clear_autofill_state() -> None:
    """Drop all panel session-state — call when starting a fresh trade."""
    import streamlit as st

    for key in (
        _RESULT_KEY,
        _ANALYSIS_KEY,
        _USAGE_KEY,
        _FIELDS_KEY,
        _APPLIED_KEY,
        PENDING_WRITES_KEY,
    ):
        st.session_state.pop(key, None)
    for key in [k for k in st.session_state if str(k).startswith("_nt_sel_")]:
        st.session_state.pop(key, None)


def drain_pending_writes() -> None:
    """Apply AI writes staged by Apply into nt_* state.

    Must be called once at the top of the New Trade page, before any form widget
    is instantiated — Streamlit forbids mutating a widget's state afterward.
    """
    import streamlit as st

    pending = st.session_state.pop(PENDING_WRITES_KEY, None)
    if pending:
        for key, value in pending.items():
            st.session_state[key] = value


def mark_field_edited(field: str) -> None:
    """on_change callback: a manual edit downgrades a field's AI-sourced marker."""
    import streamlit as st

    sourced = st.session_state.get(_FIELDS_KEY)
    if sourced:
        sourced.discard(field)


def ai_sourced_fields() -> set:
    """Semantic field names currently marked AI-sourced (for Review & Save badges)."""
    import streamlit as st

    return set(st.session_state.get(_FIELDS_KEY) or set())


def persist_analysis_for_trade(trade_id: int) -> None:
    """Persist the staged AIAnalysis to the saved trade (best-effort, save-time)."""
    import streamlit as st

    analysis = st.session_state.get(_ANALYSIS_KEY)
    usage = st.session_state.get(_USAGE_KEY)
    if not analysis or usage is None:
        return
    try:
        from src.tradelens.services.ai_analysis_service import create_or_update_analysis

        create_or_update_analysis(trade_id, analysis, usage)
    except Exception:  # noqa: BLE001 — analysis persistence is best-effort
        pass


# ---------------------------------------------------------------------------
# Rendering (Streamlit)
# ---------------------------------------------------------------------------


def _ai_available() -> bool:
    from src.tradelens.services.demo import is_demo
    from src.tradelens.utils.ai_utils import is_ai_enabled

    return is_ai_enabled() or is_demo()


def _analyze(screenshot_file, screenshot_url, strategy_profile, known_assets) -> None:
    """Run analysis on the current source and stage the result in session-state."""
    import streamlit as st

    tmp = None
    try:
        if screenshot_file is not None:
            data = screenshot_file.getvalue()  # non-consuming: Save still re-reads
            suffix = Path(screenshot_file.name).suffix.lower() or ".png"
            fd, tmp = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            source = tmp
        else:
            source = screenshot_url
        result, analysis, usage = run_autofill(source, strategy_profile, known_assets)
        st.session_state[_RESULT_KEY] = result
        st.session_state[_ANALYSIS_KEY] = analysis
        st.session_state[_USAGE_KEY] = usage
        st.session_state.pop(_APPLIED_KEY, None)
    except ScreenshotAnalysisError as exc:
        st.warning(str(exc))
    except Exception as exc:  # noqa: BLE001 — never crash the form on analysis
        st.warning(f"Couldn't analyze that screenshot: {exc}")
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _apply(result: AutofillResult, selected: list, known_assets) -> None:
    """Stage selected suggestions as pending nt_* writes and mark them AI-sourced.

    The writes are stashed (not applied directly) so the page can drain them at
    the top of the next run — before the form widgets instantiate, since Streamlit
    forbids setting a widget's state after it has been created.
    """
    import streamlit as st

    writes = build_form_writes(result.prefill, selected, known_assets)
    st.session_state[PENDING_WRITES_KEY] = writes
    sourced = st.session_state.get(_FIELDS_KEY) or set()
    sourced |= set(selected)
    st.session_state[_FIELDS_KEY] = sourced
    st.session_state[_APPLIED_KEY] = list(selected)
    st.session_state.pop(_RESULT_KEY, None)  # collapse the panel; suggestions applied
    for key in [k for k in st.session_state if str(k).startswith("_nt_sel_")]:
        st.session_state.pop(key, None)


def _display_value(field: str, value) -> str:
    if field == "confluences":
        return ", ".join(value) if value else "—"
    return str(value)


def _render_observations(observations: dict) -> None:
    import streamlit as st

    has_any = any(
        observations.get(k)
        for k in (
            "trade_quality",
            "possible_mistakes",
            "missed_opportunities",
            "notes_to_user",
            "structure",
            "matched_strategy",
            "key_zones",
        )
    )
    if not has_any:
        return
    with st.expander("AI observations (read-only — never auto-applied)"):
        tq = observations.get("trade_quality")
        if tq is not None:
            st.markdown(f"**AI quality estimate:** {tq}/10")
        if observations.get("matched_strategy"):
            st.markdown(f"**Matched strategy:** {observations['matched_strategy']}")
        if observations.get("structure"):
            st.markdown(f"**Structure:** {observations['structure']}")
        if observations.get("notes_to_user"):
            st.markdown(f"**Notes:** {observations['notes_to_user']}")
        mistakes = observations.get("possible_mistakes") or []
        if mistakes:
            st.markdown("**Possible mistakes:** " + ", ".join(str(m) for m in mistakes))
        missed = observations.get("missed_opportunities") or []
        if missed:
            st.markdown(
                "**Missed opportunities:** " + ", ".join(str(m) for m in missed)
            )
        zones = observations.get("key_zones") or []
        if zones:
            st.caption(f"{len(zones)} key zone(s) detected.")


def _render_review_panel(result: AutofillResult, known_assets) -> None:
    import streamlit as st

    st.caption(
        "🤖 AI suggestions — pick which to apply, then edit them in the steps "
        "below. Nothing is saved until you press Save."
    )

    present = [f for f in _FIELD_ORDER if f in result.prefill]
    if not present:
        st.info("AI didn't find fields it could suggest. Fill the form manually.")
    selected_default = []
    for field in present:
        label = _FIELD_LABELS[field]
        value = _display_value(field, result.prefill[field])
        checked = st.checkbox(f"{label}: {value}", value=True, key=f"_nt_sel_{field}")
        if checked:
            selected_default.append(field)

    _render_observations(result.observations)

    c1, c2, c3 = st.columns(3)
    if c1.button("Apply selected", type="primary", key="_nt_ai_apply_sel"):
        _apply(result, selected_default, known_assets)
        st.rerun()
    if c2.button("Apply all", key="_nt_ai_apply_all"):
        _apply(result, present, known_assets)
        st.rerun()
    if c3.button("Dismiss", key="_nt_ai_dismiss"):
        st.session_state.pop(_RESULT_KEY, None)
        for key in [k for k in st.session_state if str(k).startswith("_nt_sel_")]:
            st.session_state.pop(key, None)
        st.rerun()


def render_autofill_review(
    *,
    screenshot_file,
    screenshot_url: Optional[str],
    strategy_profile: Optional[dict],
    known_assets: Iterable[str],
) -> None:
    """Render the analyze button + AI review/apply panel for the New Trade page."""
    import streamlit as st

    st.markdown("**AI Autofill (optional)**")

    if not _ai_available():
        st.info(
            "🤖 AI autofill is off. Add your Anthropic API key in Settings to get "
            "post-trade chart suggestions. You can still fill the form manually."
        )
        return

    has_source = screenshot_file is not None or bool(screenshot_url)
    if not has_source:
        st.caption("Add a screenshot or image URL above to get AI suggestions.")
        return

    applied = st.session_state.get(_APPLIED_KEY)
    if applied:
        names = ", ".join(_FIELD_LABELS.get(f, f) for f in applied)
        st.success(f"✅ Applied to the form: {names}. Edit them in the steps below.")

    has_result = _RESULT_KEY in st.session_state
    label = "Re-analyze screenshot" if has_result else "🔍 Analyze screenshot"
    if st.button(label, key="_nt_ai_analyze"):
        with st.spinner("Analyzing your chart…"):
            _analyze(screenshot_file, screenshot_url, strategy_profile, known_assets)
        st.rerun()

    result = st.session_state.get(_RESULT_KEY)
    if isinstance(result, AutofillResult):
        _render_review_panel(result, list(known_assets))

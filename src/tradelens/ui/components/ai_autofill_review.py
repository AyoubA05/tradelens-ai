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
from src.tradelens.services.ai_overlay import (
    PROVENANCE_TEXT,
    TradeOverlay,
    descriptive_section,
    field_provenance,
    parse_trade_overlay,
)
from src.tradelens.services.ai_screenshot_service import analyze_source
from src.tradelens.services.assets import OTHER, normalize_symbol
from src.tradelens.services.vision import (
    ScreenshotAnalysisError,
    analyze_screenshot_v3,
    check_screenshot_quality,
)

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
_OVERLAY_KEY = "_nt_ai_overlay"  # TradeOverlay from the last analysis (Phase 3)
# "Keep reviewing" dismisses the modal but keeps the detection staged for reopen.
_DIALOG_DISMISSED_KEY = "_nt_ai_dialog_dismissed"
_QUALITY_KEY = "_nt_ai_quality"  # list[str] pre-check warnings for this analysis
_ERROR_KEY = "_nt_ai_error"  # analysis failure message (survives the rerun)
_SRC_SIG_KEY = "_nt_ai_src_sig"  # last auto-analyzed source (Item 2 auto-trigger)
_OUTCOME_KEY = "_nt_ai_outcome"  # "accepted" | "rejected" — the trader's decision
_EDITED_KEY = "_nt_ai_edited"  # set[str] of AI-applied fields edited afterwards

# Entry/stop pre-check only when the model is confident; everything else opt-in.
AUTOCHECK_FIELDS = ("entry_price", "stop_price")
AUTOCHECK_MIN_CONFIDENCE = 0.70

# Overlay price field -> nt_* widget key. Direction is intentionally absent —
# it's display-only; the form infers direction from the applied entry/stop.
_OVERLAY_FIELD_TO_KEY = {
    "entry_price": "nt_entry",
    "stop_price": "nt_stop",
    "tp_price": "nt_tp",
    "exit_price": "nt_exit",
}
_OVERLAY_FIELD_LABELS = {
    "direction": "Direction",
    "entry_price": "Entry",
    "stop_price": "Stop",
    "tp_price": "Take Profit",
    "exit_price": "Exit",
    "entry_time": "Entry Time",
}

# Keep in sync with the Entry Time default in pages/1_NewTrade.py — an untouched
# default (or empty) may accept the AI's estimate; anything else the trader typed.
_ENTRY_TIME_DEFAULT = "09:30"


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


def build_overlay_writes(overlay: TradeOverlay, selected: Iterable[str]) -> dict:
    """Map accepted overlay PRICES (+ opt-in PnL) to {nt_key: value}.

    Never writes direction (Phase-3 decision 5): the form infers direction from the
    applied entry/stop. PnL is opt-in and, when selected, writes the real ``nt_pnl``
    key. Risk/reward ratio is cross-check only and is never written (the form
    derives R from prices). Only selected, non-null values write.
    """
    selected = set(selected)
    writes: dict = {}
    for field, key in _OVERLAY_FIELD_TO_KEY.items():
        if field in selected:
            value = getattr(overlay, field, None)
            if value is not None:
                # Item 7: the form's price fields are exact-precision TEXT
                # inputs, so applied prices are written as strings. str() keeps
                # the full value (%g would truncate 30433.25 to 6 sig figs).
                writes[key] = str(value)
    if "pnl" in selected and getattr(overlay, "pnl", None) is not None:
        writes["nt_pnl"] = overlay.pnl
    # Item 4: approximate entry time — opt-in like the prices.
    if "entry_time" in selected and getattr(overlay, "entry_time_approx", None):
        writes["nt_entry_time"] = overlay.entry_time_approx
    return writes


def entry_time_write_allowed(current_value) -> bool:
    """Item 4: never overwrite an entry time the trader already typed.

    The field starts at the page default; an empty or untouched-default value
    may accept the AI estimate, anything else is the trader's and wins.
    """
    if current_value is None:
        return True
    s = str(current_value).strip()
    return not s or s == _ENTRY_TIME_DEFAULT


def should_autocheck(field: str, confidence) -> bool:
    """Default-checked state for a detected-markup checkbox.

    Only entry/stop auto-check, and only at >= 0.70 confidence — below that the
    trader must opt in explicitly. Junk/missing confidence never auto-checks.
    """
    if field not in AUTOCHECK_FIELDS:
        return False
    try:
        return float(confidence) >= AUTOCHECK_MIN_CONFIDENCE
    except (TypeError, ValueError):
        return False


def build_review_outcome(outcome, applied_fields, edited_fields) -> Optional[dict]:
    """The trader's review decision as a persistable record, or None.

    outcome is "accepted" or "rejected" (what the trader clicked); an accept
    followed by manual edits of AI-applied fields becomes "accepted_with_edits".
    Returns None when the trader never made a decision (nothing to record).
    """
    if not outcome:
        return None
    applied = list(applied_fields or [])
    edited = sorted(set(edited_fields or []))
    final = "accepted_with_edits" if outcome == "accepted" and edited else outcome
    return {"outcome": final, "applied_fields": applied, "edited_fields": edited}


def observation_summary(observations, max_len: int = 160) -> Optional[str]:
    """One-line default view of the AI observations (full text stays available).

    Prefers the conversational notes (truncated on a word boundary), falls back
    to the quality estimate, and returns None when there is nothing to say.
    """
    if not isinstance(observations, dict):
        return None
    notes = observations.get("notes_to_user")
    if isinstance(notes, str) and notes.strip():
        notes = notes.strip()
        if len(notes) <= max_len:
            return notes
        cut = notes[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:.")
        return f"{cut}…"
    tq = observations.get("trade_quality")
    if tq is not None:
        return f"AI quality estimate: {tq}/10"
    return None


def run_autofill(
    source,
    strategy_profile: Optional[dict],
    known_assets: Optional[Iterable[str]] = None,
) -> tuple[AutofillResult, TradeOverlay, dict, object]:
    """Analyze a screenshot (screenshot_v3) into descriptive + overlay results.

    ``source`` is a local image path or a direct image URL. Returns
    (autofill_result, trade_overlay, raw_analysis, usage):
      * autofill_result drives the descriptive review panel (Phase 1 mapping over
        the flattened ``descriptive`` section — direction/prices can never appear).
      * trade_overlay drives the separate "Detected from markup" section.
      * raw_analysis + usage are persisted to AIAnalysis after the trade saves.
    Raises ScreenshotAnalysisError for an unreadable source.
    """
    analysis, usage = analyze_source(
        source, {}, strategy_profile, analyzer=analyze_screenshot_v3
    )
    result = map_analysis_to_form(
        descriptive_section(analysis), known_assets=known_assets
    )
    overlay = parse_trade_overlay(analysis)
    return result, overlay, analysis, usage


# ---------------------------------------------------------------------------
# Session-state helpers (Streamlit)
# ---------------------------------------------------------------------------


def clear_autofill_state() -> None:
    """Drop all panel session-state — call when starting a fresh trade."""
    import streamlit as st

    for key in (
        _RESULT_KEY,
        _OVERLAY_KEY,
        _ANALYSIS_KEY,
        _USAGE_KEY,
        _FIELDS_KEY,
        _APPLIED_KEY,
        _DIALOG_DISMISSED_KEY,
        _QUALITY_KEY,
        _ERROR_KEY,
        _SRC_SIG_KEY,
        _OUTCOME_KEY,
        _EDITED_KEY,
        PENDING_WRITES_KEY,
    ):
        st.session_state.pop(key, None)
    for key in [
        k
        for k in st.session_state
        if str(k).startswith("_nt_sel_") or str(k).startswith("_nt_ov_")
    ]:
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
    """on_change callback: a manual edit downgrades a field's AI-sourced marker.

    Also records the edit for outcome tracking — an accepted-then-edited field
    turns the review outcome into "accepted_with_edits" at save time.
    """
    import streamlit as st

    sourced = st.session_state.get(_FIELDS_KEY)
    if sourced and field in sourced:
        sourced.discard(field)
        edited = st.session_state.setdefault(_EDITED_KEY, set())
        edited.add(field)


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

        # Flatten descriptive to top-level (so the existing column denormalization
        # in create_or_update_analysis still populates) and keep the full
        # trade_overlay in raw_response_json for inspection. No schema change.
        to_persist = dict(descriptive_section(analysis))
        if isinstance(analysis, dict):
            to_persist["trade_overlay"] = analysis.get("trade_overlay", {})
        # Outcome tracking: how the trader handled the suggestions (accepted /
        # accepted_with_edits / rejected + which fields changed). Lives inside
        # raw_response_json — reuses the existing row, no schema change.
        record = build_review_outcome(
            st.session_state.get(_OUTCOME_KEY),
            st.session_state.get(_APPLIED_KEY) or [],
            st.session_state.get(_EDITED_KEY) or (),
        )
        if record:
            to_persist["review_outcome"] = record
        create_or_update_analysis(
            trade_id, to_persist, usage, prompt_version="screenshot_v3"
        )
    except Exception:  # noqa: BLE001 — analysis persistence is best-effort
        pass


# ---------------------------------------------------------------------------
# Rendering (Streamlit)
# ---------------------------------------------------------------------------


def _ai_available() -> bool:
    from src.tradelens.utils.ai_utils import ai_available

    return ai_available()


def _analyze(screenshot_file, screenshot_url, strategy_profile, known_assets) -> None:
    """Run analysis on the current source and stage the result in session-state."""
    import streamlit as st

    st.session_state.pop(_ERROR_KEY, None)
    st.session_state.pop(_QUALITY_KEY, None)
    tmp = None
    try:
        if screenshot_file is not None:
            data = screenshot_file.getvalue()  # non-consuming: Save still re-reads
            suffix = Path(screenshot_file.name).suffix.lower() or ".png"
            fd, tmp = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            source = tmp
            # Quality pre-check (local, free). Warn on likely-degraded extraction;
            # block only when the file fundamentally isn't an image. URL sources
            # skip this — we never fetch URLs ourselves (SSRF hardening).
            quality = check_screenshot_quality(tmp)
            if not quality.usable:
                st.session_state[_ERROR_KEY] = (
                    "This screenshot can't be analyzed: " + " ".join(quality.warnings)
                )
                return
            if quality.warnings:
                st.session_state[_QUALITY_KEY] = list(quality.warnings)
        else:
            source = screenshot_url
        result, overlay, analysis, usage = run_autofill(
            source, strategy_profile, known_assets
        )
        st.session_state[_RESULT_KEY] = result
        st.session_state[_OVERLAY_KEY] = overlay
        st.session_state[_ANALYSIS_KEY] = analysis
        st.session_state[_USAGE_KEY] = usage
        st.session_state.pop(_APPLIED_KEY, None)
        st.session_state.pop(_OUTCOME_KEY, None)
        st.session_state.pop(_EDITED_KEY, None)
        _clear_selection_state()  # fresh defaults for the new detection
    except ScreenshotAnalysisError as exc:
        st.session_state[_ERROR_KEY] = str(exc)
    except Exception as exc:  # noqa: BLE001 — never crash the form on analysis
        st.session_state[_ERROR_KEY] = f"Couldn't analyze that screenshot: {exc}"
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _clear_selection_state() -> None:
    import streamlit as st

    for key in [
        k
        for k in st.session_state
        if str(k).startswith("_nt_sel_") or str(k).startswith("_nt_ov_")
    ]:
        st.session_state.pop(key, None)


def _apply_all(
    result: Optional[AutofillResult],
    overlay: Optional[TradeOverlay],
    sel_desc: list,
    sel_prices: list,
    known_assets,
) -> None:
    """Stage the confirmed descriptive fields AND prices as pending nt_* writes.

    Writes are stashed (not applied directly) so the page drains them at the top
    of the next run — before the form widgets instantiate, since Streamlit forbids
    setting a widget's state after it has been created. Direction is never written
    (Phase-3 decision 5) — the form infers it from the applied entry/stop.
    """
    import streamlit as st

    writes: dict = {}
    if isinstance(result, AutofillResult):
        writes.update(build_form_writes(result.prefill, sel_desc, known_assets))
    if isinstance(overlay, TradeOverlay):
        writes.update(build_overlay_writes(overlay, sel_prices))
    # Item 4: an entry time the trader already typed always wins over the AI's.
    if "nt_entry_time" in writes and not entry_time_write_allowed(
        st.session_state.get("nt_entry_time")
    ):
        writes.pop("nt_entry_time")

    st.session_state[PENDING_WRITES_KEY] = writes
    sourced = st.session_state.get(_FIELDS_KEY) or set()
    sourced |= set(sel_desc) | set(sel_prices)
    st.session_state[_FIELDS_KEY] = sourced
    st.session_state[_APPLIED_KEY] = list(sel_desc) + list(sel_prices)
    # Applying with every suggestion unchecked is a decline, not an accept.
    st.session_state[_OUTCOME_KEY] = (
        "accepted" if (sel_desc or sel_prices) else "rejected"
    )
    st.session_state.pop(_EDITED_KEY, None)
    st.session_state.pop(_RESULT_KEY, None)
    st.session_state.pop(_OVERLAY_KEY, None)
    st.session_state.pop(_DIALOG_DISMISSED_KEY, None)
    _clear_selection_state()


def _discard_detection() -> None:
    """Close the detection dialog without writing anything to the form."""
    import streamlit as st

    st.session_state.pop(_RESULT_KEY, None)
    st.session_state.pop(_OVERLAY_KEY, None)
    st.session_state.pop(_DIALOG_DISMISSED_KEY, None)
    _clear_selection_state()


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
    # Compact-first: one summary line by default; the full notes, possible
    # mistakes, and missed opportunities stay one click away, untruncated.
    summary = observation_summary(observations)
    if summary:
        st.markdown(f"**AI observations:** {summary}")
    with st.expander("Full AI observations (read-only — never auto-applied)"):
        tq = observations.get("trade_quality")
        if tq is not None:
            st.markdown(f"**AI quality estimate:** {tq}/10")
        if observations.get("notes_to_user"):
            st.markdown(f"**Notes:** {observations['notes_to_user']}")
        if observations.get("matched_strategy"):
            st.markdown(f"**Matched strategy:** {observations['matched_strategy']}")
        if observations.get("structure"):
            st.markdown(f"**Structure:** {observations['structure']}")
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


def _confidence_str(value) -> str:
    return f" · {int(round(value * 100))}%" if value is not None else ""


def _select_descriptive(result: AutofillResult) -> list:
    """Render descriptive-field checkboxes; return the selected field names."""
    import streamlit as st

    present = [f for f in _FIELD_ORDER if f in result.prefill]
    if not present:
        st.caption("No descriptive fields were detected.")
        return []
    selected = []
    for field in present:
        label = _FIELD_LABELS[field]
        value = _display_value(field, result.prefill[field])
        if st.checkbox(f"{label}: {value}", value=True, key=f"_nt_sel_{field}"):
            selected.append(field)
    return selected


def _overlay_has_content(overlay) -> bool:
    """True when the overlay carries anything worth showing (prices, PnL, RR, …)."""
    return (
        isinstance(overlay, TradeOverlay)
        and overlay.source != "none"
        and (
            overlay.has_prices()
            or overlay.pnl is not None
            or bool(overlay.risk_reward_ratio)
            or bool(overlay.direction)
            or bool(overlay.overall_confidence)
            or bool(overlay.visible_labels)
            or bool(overlay.entry_time_approx)
        )
    )


def _select_prices(overlay: TradeOverlay) -> list:
    """Render the detected-markup checkboxes; return the selected fields.

    Prices and PnL are opt-in (default OFF) and get written on Apply. Direction,
    risk/reward ratio, overall confidence, and the OCR labels are cross-check
    context only — never part of the returned selection, so never written.
    """
    import streamlit as st

    if not _overlay_has_content(overlay):
        return []
    st.markdown("**Detected from chart markup**")
    st.caption(
        "Read from your drawn trade box — confirm each value before applying. "
        "Direction is inferred from the prices you apply, not written here."
    )
    if overlay.direction:
        conf = _confidence_str(overlay.confidence.get("direction"))
        st.caption(
            f"AI sees direction: **{overlay.direction.title()}**{conf} "
            "(cross-check only — not written)"
        )
    selected = []
    missing = []
    for field in _OVERLAY_FIELD_TO_KEY:  # entry, stop, tp, exit in order
        value = getattr(overlay, field)
        label = _OVERLAY_FIELD_LABELS[field]
        if value is None:
            missing.append(label)
            continue
        conf = overlay.confidence.get(field)
        conf_txt = (
            f"{int(round(conf * 100))}% confidence"
            if conf is not None
            else "confidence unknown"
        )
        provenance = PROVENANCE_TEXT[field_provenance(overlay, field)]
        # Entry/stop pre-check at >= 0.70 confidence; everything else opt-in.
        # Nothing is written until the trader clicks Apply.
        if st.checkbox(
            f"{label}: {value} · {conf_txt}",
            value=should_autocheck(field, conf),
            key=f"_nt_ov_{field}",
            help=f"This value was {provenance}.",
        ):
            selected.append(field)
        st.caption(f"↳ {provenance}")
    # Item 4: approximate entry time — opt-in (never auto-checked), clearly
    # badged as an estimate, and never applied over a trader-typed time.
    if overlay.entry_time_approx:
        conf = overlay.confidence.get("entry_time")
        conf_txt = (
            f"{int(round(conf * 100))}% confidence"
            if conf is not None
            else "confidence unknown"
        )
        if st.checkbox(
            f"Entry Time: {overlay.entry_time_approx} · {conf_txt}",
            value=False,
            key="_nt_ov_entry_time",
            help="Approximate time read from the chart's time axis or timestamp "
            "bar. It never replaces a time you typed yourself.",
        ):
            selected.append("entry_time")
        st.caption("↳ Estimated from chart")
    if missing:
        st.caption("Not visible on the chart: " + ", ".join(missing))
    # PnL: opt-in (default OFF), shown only when a closed P&L was visibly read.
    if overlay.pnl is not None:
        if st.checkbox(f"P&L: {overlay.pnl}", value=False, key="_nt_ov_pnl"):
            selected.append("pnl")
    # Cross-check context — never written into the form.
    if overlay.risk_reward_ratio:
        st.caption(
            f"AI sees risk/reward ≈ **{overlay.risk_reward_ratio}** "
            "(cross-check only — R is derived from your prices)"
        )
    if overlay.overall_confidence:
        st.caption(f"Overall extraction confidence: {overlay.overall_confidence}")
    if overlay.visible_labels:
        st.caption("Labels read: " + ", ".join(overlay.visible_labels))
    return selected


def _open_detection_dialog(
    result: Optional[AutofillResult],
    overlay: Optional[TradeOverlay],
    known_assets: list,
) -> None:
    """Open the 'Here is what the AI detected' confirmation modal (Change A).

    Nothing is written to the form until the trader confirms with Apply — the
    screenshot auto-detect / user-confirms safety contract.
    """
    import streamlit as st

    @st.dialog("This is what the AI detected")
    def _dlg() -> None:
        st.caption(
            "Review what the AI read from your chart, then choose. Nothing is "
            "written to your form until you apply it — and every field stays "
            "editable afterward."
        )
        for warning in st.session_state.get(_QUALITY_KEY) or []:
            st.warning(f"Screenshot quality: {warning}")
        instrument = (
            (result.observations or {}).get("instrument_name")
            if isinstance(result, AutofillResult)
            else None
        )
        if instrument:
            st.caption(f"Instrument: {instrument}")
        sel_desc = (
            _select_descriptive(result) if isinstance(result, AutofillResult) else []
        )
        if isinstance(result, AutofillResult):
            _render_observations(result.observations)
        sel_prices = (
            _select_prices(overlay) if isinstance(overlay, TradeOverlay) else []
        )
        if not _overlay_has_content(overlay):
            st.caption(
                "No trade-box markup was visibly detected on this chart, so no "
                "prices can be suggested. You can still enter them manually."
            )

        st.divider()
        c1, c2, c3 = st.columns(3)
        if c1.button("Apply detected fields", type="primary", key="_nt_ai_apply"):
            _apply_all(result, overlay, sel_desc, sel_prices, known_assets)
            st.rerun()
        if c2.button("Keep reviewing", key="_nt_ai_keep"):
            # Dismiss the modal but keep the detection staged for reopen.
            st.session_state[_DIALOG_DISMISSED_KEY] = True
            st.rerun()
        if c3.button("Cancel", key="_nt_ai_cancel"):
            # Outcome tracking: an explicit cancel is a rejection of the
            # suggestions (the analysis itself still persists with the trade).
            st.session_state[_OUTCOME_KEY] = "rejected"
            st.session_state[_APPLIED_KEY] = []
            _discard_detection()
            st.rerun()

    _dlg()


def _has_detection(result, overlay) -> bool:
    """True when the AI surfaced anything worth confirming (fields or overlay)."""
    has_fields = isinstance(result, AutofillResult) and any(
        f in result.prefill for f in _FIELD_ORDER
    )
    return bool(has_fields or _overlay_has_content(overlay))


def _source_signature(screenshot_file, screenshot_url):
    """Identity of the current screenshot source, for the auto-trigger (Item 2).

    A new signature means a new file/URL the trader just provided — analysis
    starts automatically, exactly once per source (an error never loops).
    The file wins over the URL, matching _analyze's precedence.
    """
    if screenshot_file is not None:
        fid = getattr(screenshot_file, "file_id", None)
        return ("file", fid or (screenshot_file.name, screenshot_file.size))
    if screenshot_url:
        return ("url", screenshot_url)
    return None


def render_autofill_review(
    *,
    screenshot_file,
    screenshot_url: Optional[str],
    strategy_profile: Optional[dict],
    known_assets: Iterable[str],
) -> None:
    """Render the auto-running analysis and, after it, the AI detection dialog."""
    import streamlit as st

    st.markdown("**AI Autofill (optional)**")
    st.caption(
        "Post-trade chart review — suggestions you confirm before they touch "
        "the form. Never signals or entries."
    )

    if not _ai_available():
        st.info(
            "AI autofill is off. Add your Anthropic API key in Settings to get "
            "post-trade chart suggestions. You can still fill the form manually."
        )
        return

    has_source = screenshot_file is not None or bool(screenshot_url)
    if not has_source:
        st.caption("Add a screenshot or image URL above to get AI suggestions.")
        return

    applied = st.session_state.get(_APPLIED_KEY)
    if applied:
        names = ", ".join(
            _FIELD_LABELS.get(f, _OVERLAY_FIELD_LABELS.get(f, f)) for f in applied
        )
        st.success(f"✅ Applied to the form: {names}. Edit them in the steps below.")

    # Auto-trigger (Item 2): analysis starts the moment a new source appears —
    # file drop, file browse, or committed URL paste — with no button press.
    # The signature marks the attempt first, so a completed run or an error
    # never re-triggers for the same source. The spinner renders right here,
    # where the results will appear; the upload area above is untouched.
    sig = _source_signature(screenshot_file, screenshot_url)
    if sig is not None and st.session_state.get(_SRC_SIG_KEY) != sig:
        st.session_state[_SRC_SIG_KEY] = sig
        with st.spinner("Analyzing your chart…"):
            _analyze(screenshot_file, screenshot_url, strategy_profile, known_assets)
        st.rerun()

    # Manual re-run stays available once a result or error exists (e.g. after
    # the trader redraws markup and re-uploads the same file).
    has_activity = isinstance(
        st.session_state.get(_RESULT_KEY), AutofillResult
    ) or st.session_state.get(_ERROR_KEY)
    if has_activity and st.button("Re-analyze screenshot", key="_nt_ai_analyze"):
        with st.spinner("Analyzing your chart…"):
            _analyze(screenshot_file, screenshot_url, strategy_profile, known_assets)
        st.rerun()

    # Analysis errors are stashed in session-state so they survive the rerun.
    error = st.session_state.get(_ERROR_KEY)
    if error:
        st.warning(error)

    # Result survives reruns in session_state. The dialog opens whenever a fresh
    # detection is staged; "Keep reviewing" dismisses it but keeps the detection so
    # the trader can look at the form and reopen it (Change A).
    result = st.session_state.get(_RESULT_KEY)
    overlay = st.session_state.get(_OVERLAY_KEY)
    if _has_detection(result, overlay):
        if st.session_state.get(_DIALOG_DISMISSED_KEY):
            st.caption("AI detection ready — not yet applied.")
            if st.button("Review AI detection", key="_nt_ai_reopen"):
                st.session_state.pop(_DIALOG_DISMISSED_KEY, None)
                st.rerun()
        else:
            _open_detection_dialog(result, overlay, list(known_assets))
    elif isinstance(result, AutofillResult):
        st.info("AI didn't find fields it could suggest. Fill the form manually.")
        _discard_detection()

"""
Insights & Review — Pattern Insights + the unified Weekly Recap (Item 10).

One destination for reflection: deterministic Pattern Insights (no AI call),
the unified Weekly Recap — ONE AI call that receives both the weekly trade data
and the deterministic pattern statistics and returns performance/process review
plus observed patterns — and the on-demand Daily Debrief. The recap auto-runs on
page load and a saved recap is reused instead of paying for a new call.
A domain failure (WeeklyReviewError, DebriefError) surfaces its own specific,
trader-safe explanation. An unexpected one surfaces fixed generic recovery copy
and logs the exception, because driver and network text can carry a DSN or a key.

This is post-trade reflection only — never live signals, predictions, or advice.
"""

import logging
import sys
import datetime
from html import escape
from pathlib import Path

# parents[4] of src/tradelens/ui/pages/*.py  →  project root
_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.debrief import (  # noqa: E402
    DebriefError,
    generate_debrief,
)
from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.patterns import (  # noqa: E402
    generate_insights,
)
from src.tradelens.services.strategy import (  # noqa: E402
    get_active_strategy,
)
from src.tradelens.services.activation import (  # noqa: E402
    TRADES_FOR_REVIEW,
    activation_status,
)
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.weekly import (  # noqa: E402
    WeeklyReviewError,
    generate_weekly_review,
    get_weekly_review,
    save_weekly_review,
    week_bounds,
)
from src.tradelens.ui.components.auth import current_user_id, require_auth  # noqa: E402
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.sidebar import (  # noqa: E402
    render_sidebar,
    route_href,
)
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import error_box  # noqa: E402
from src.tradelens.ui.components.review_reader import (  # noqa: E402
    period_stats,
    render_review_reader,
    view_from_markdown,
    view_from_note,
)
from src.tradelens.ui.components.workspace import (  # noqa: E402
    EvidenceItem,
    MetricItem,
    ResearchFinding,
    ResearchNote,
    render_kpi_strip,
    render_note_skeleton,
    render_section_header,
    render_workspace_header,
)
from src.tradelens.ui.design_system import (  # noqa: E402
    inject_design_system,
    render_empty_state,
)
from src.tradelens.utils.ai_utils import is_ai_enabled  # noqa: E402

st.set_page_config(page_title="Insights & Review", layout="wide")
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()
uid = current_user_id()
render_demo_banner()
render_sidebar()
# ── Lenses ────────────────────────────────────────────────────────
# Three notes, one at a time. Stacked, they were a feed to scroll; each is
# actually a separate question with a separate period.
AI_REVIEW_LENSES = ("Patterns", "Weekly Recap", "Daily Debrief")
_LENS_KEY = "ai_review_lens"
_LENS_WIDGET_KEY = "ai_review_lens_pick"

_LENS_QUESTIONS = {
    "Patterns": "What keeps repeating in the journal?",
    "Weekly Recap": "How did the completed week go?",
    "Daily Debrief": "What happened on one trading day?",
}

st.markdown(
    render_workspace_header(
        "AI Reviews",
        "Evidence-backed reading of your own journal. Reflection only — "
        "never signals or advice.",
    ),
    unsafe_allow_html=True,
)


def _error_box(message: str) -> None:
    """Readable, persistent inline error block (shared ui.error_box builder).

    Used instead of a transient st.toast so a failed AI call surfaces a specific,
    lasting reason the user can read and act on (Part 3 requirement).
    """
    st.markdown(error_box(message), unsafe_allow_html=True)


_DF_COLS = [
    "id",
    "trade_date",
    "day_of_week",
    "session",
    "asset",
    "setup_type",
    "rr_realized",
    "pnl",
    "result",
    "killzone",
    "confirmation_model",
    "mistake_tags",
    "htf_bias",
    "direction",
    "followed_rules",
]


def _load_df() -> pd.DataFrame:
    trades = get_trades(user_id=uid)
    df = pd.DataFrame([{c: getattr(t, c, None) for c in _DF_COLS} for t in trades])
    if df.empty:
        return df
    return df[df["trade_date"].notna() & (df["trade_date"] != "")].reset_index(
        drop=True
    )


df = _load_df()
if df.empty and is_demo():
    df = get_demo_df()

_strategy = get_active_strategy(uid) if uid is not None else None
_ai_on = is_ai_enabled() or is_demo()

if df.empty:
    st.markdown(
        render_empty_state(
            "psychology",
            "No trades yet",
            "Log a few trades and the AI will start reviewing your journal.",
        ),
        unsafe_allow_html=True,
    )
    # page_link needs the multipage registry, which standalone AppTest boots
    # don't build — degrade to a plain slug link (sidebar pattern).
    try:
        st.page_link("pages/1_NewTrade.py", label="Log a trade →")
    except Exception:  # noqa: BLE001 — registry-less boots/tests only
        _new_trade_href = escape(
            route_href("/NewTrade", st.query_params.get("auth")), quote=True
        )
        st.markdown(
            f'<a href="{_new_trade_href}" target="_self">Log a trade →</a>',
            unsafe_allow_html=True,
        )
    st.stop()


# ══════════════════════════════════════════════════════════════════
# Shared note plumbing
# ══════════════════════════════════════════════════════════════════
_log = logging.getLogger(__name__)

# A domain error (WeeklyReviewError, DebriefError) carries a message written
# for the trader and is shown. Anything else is a driver, network or parser
# message that can carry a DSN, an API key or a fragment of the row, so it
# goes to the log and the trader gets this instead.
_AI_FAILED = "The review could not be generated. Try again."

_CONF_BY_SAMPLE = ((20, "high"), (10, "medium"))


def _confidence_for(trades: int) -> str:
    """How much weight a sample can carry. Matches the prompt's bands."""
    for threshold, level in _CONF_BY_SAMPLE:
        if trades >= threshold:
            return level
    return "low"


def _evidence_used(review: dict) -> list:
    """What the review was based on — never how it was produced.

    Model reasoning, prompt content, token counts and call cost are
    operator data. Cost stays recorded for the Settings accounting view.
    """
    stats = review.get("stats") or {}
    trades = int(stats.get("trades") or 0)
    rows = [f"Trades reviewed: {trades}"]
    if review.get("week_start"):
        rows.append(f"Period: {review['week_start']}")
    rows.append(f"Strategy profile: {'included' if _strategy else 'not included'}")
    return rows


def _regenerating() -> None:
    """Inline, polite progress that leaves the prior note exactly where it is.

    Not `render_note_skeleton`: the skeleton stands in for a note that is not
    there yet, and using it during a regeneration would replace the review the
    trader is reading with grey bars. A status line changes nothing above it,
    so the page does not jump.
    """
    st.markdown(
        '<p class="tl-note-updating" role="status" aria-live="polite">'
        "Updating review…</p>",
        unsafe_allow_html=True,
    )


def _note_stats(stats: dict) -> None:
    """The period's numbers as one ruled strip above the note."""
    if not stats:
        return
    # PF convention (app-wide): wins/no losses → ∞; no wins AND no losses
    # (breakeven-only period, 0/0) → N/A; otherwise the numeric ratio.
    pf = stats.get("profit_factor")
    if not stats.get("trades"):
        pf_text = "N/A"
    elif pf is None:
        pf_text = "∞"
    elif pf == 0.0 and not stats.get("total_pnl"):
        pf_text = "N/A"
    else:
        pf_text = f"{float(pf):.1f}x"

    net = float(stats.get("total_pnl") or 0.0)
    leak = float(stats.get("total_edge_leak") or 0.0)
    st.markdown(
        render_kpi_strip(
            [
                MetricItem("Trades", str(int(stats.get("trades") or 0))),
                MetricItem("Win rate", f"{(stats.get('win_rate') or 0.0) * 100:.1f}%"),
                MetricItem(
                    "Net P&L",
                    f"{'-' if net < 0 else ''}${abs(net):,.2f}",
                    tone=(
                        "positive" if net > 0 else "negative" if net < 0 else "neutral"
                    ),
                ),
                MetricItem("Profit factor", pf_text),
                MetricItem(
                    "Edge leak",
                    f"{'-' if leak < 0 else ''}${abs(leak):,.2f}",
                    tone="negative" if leak < 0 else "neutral",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )


def _render_generated_note(review: dict, title: str, sample: str, *, key: str) -> None:
    """A generated review through the one reading shell.

    content_md is a multi-section Markdown document. It reaches the shell as
    Markdown and is rendered by Streamlit with unsafe HTML OFF — model output
    must never take an HTML-allowing path. The evidence treatment is our own
    markup with escaped values, built separately by `build_note_regions`.
    """
    stats = review.get("stats") or {}
    trades = int(stats.get("trades") or 0)
    render_review_reader(
        st,
        view_from_markdown(
            title=title,
            sample=sample,
            content_md=review.get("content_md"),
            evidence=EvidenceItem(
                evidence="Your own journalled trades for this period",
                sample=sample,
                confidence=_confidence_for(trades),
                limitation=(
                    "Small sample — read this as a description, not a rule."
                    if trades < 5
                    else None
                ),
            ),
            evidence_used=_evidence_used(review),
        ),
        state_key=key,
    )


# ══════════════════════════════════════════════════════════════════
# Lens 1 — Patterns (deterministic, always on — no AI call)
# ══════════════════════════════════════════════════════════════════
# The former separate AI pattern-cards call is retired — pattern signals
# come from the single Weekly Recap call, which receives the weekly stats
# AND the pattern statistics.
_TYPE_LIMITATION = {
    "negative": "A recurring cost, not a verdict on the setup itself.",
    "positive": "Describes what happened, not what will.",
}


def _render_patterns_lens() -> None:
    insights = generate_insights(df, _strategy)
    sample = f"n={len(df)} trades"
    # D7: Weekly and Daily opened with the period strip and Patterns opened
    # with nothing, so the same page answered "how big is this sample" in two
    # different ways. Same builder, same five cells, same conventions — the
    # figures come from the metrics service, not from this page.
    _note_stats(period_stats(df))

    if not insights:
        st.markdown(
            render_empty_state(
                "pattern",
                "No repeating patterns yet",
                f"Journal {max(0, 5 - len(df))} more completed trades and the "
                "recurring ones start to separate from noise.",
            ),
            unsafe_allow_html=True,
        )
        return

    # The strongest supported observation becomes the thesis; the rest are
    # the numbered findings that back it. A page of equally weighted cards
    # never said which one mattered most.
    ordered = sorted(
        insights,
        key=lambda i: {"high": 0, "medium": 1, "low": 2}.get(
            str(i.get("confidence")), 3
        ),
    )
    lead, rest = ordered[0], ordered[1:5]

    findings = tuple(
        ResearchFinding(
            number=n,
            title=str(ins.get("title") or ""),
            body=str(ins.get("body") or ""),
            evidence=EvidenceItem(
                evidence=str(ins.get("title") or ""),
                sample=sample,
                confidence=str(ins.get("confidence") or "low"),
                limitation=_TYPE_LIMITATION.get(str(ins.get("type"))),
            ),
        )
        for n, ins in enumerate(rest, start=1)
    )

    # A review action, never a trade action: what to go and re-read.
    actions = [f"Re-read the trades behind “{lead.get('title')}” in the Journal."]
    if findings:
        actions.append(f"Check whether “{findings[0].title}” still holds next week.")

    # Through the same shell as the generated lenses. `render_research_note`
    # embeds an Evidence Rail inside EVERY numbered finding, so four findings
    # stacked four rails — against §7.2's "once per note, not under every
    # paragraph". The shell shows one section at a time and one rail.
    render_review_reader(
        st,
        view_from_note(
            ResearchNote(
                title="What keeps repeating",
                thesis=str(lead.get("body") or lead.get("title") or ""),
                findings=findings,
                actions=tuple(actions),
                evidence_used=(
                    f"Trades reviewed: {len(df)}",
                    f"Strategy profile: {'included' if _strategy else 'not included'}",
                    "Computed from your journal — no AI call",
                ),
                sample=sample,
                limitation=(
                    "Fewer than five trades — these describe a handful of "
                    "records, not a pattern."
                    if len(df) < 5
                    else ""
                ),
            )
        ),
        state_key="_ins_patterns_section",
    )


# ══════════════════════════════════════════════════════════════════
# Lens 2 — Weekly Recap (one AI call; auto-run; cached)
# ══════════════════════════════════════════════════════════════════
def _default_week(frame: pd.DataFrame) -> datetime.date:
    """Week of the latest trade, so the page opens on a week worth reviewing."""
    try:
        latest = pd.to_datetime(frame["trade_date"], errors="coerce").max()
        if pd.notna(latest):
            return latest.date()
    except Exception:  # noqa: BLE001
        pass
    return datetime.date.today()


def _trade_rows_for_activation():
    """The page's own user-scoped frame as row objects, for milestone counting."""
    from types import SimpleNamespace

    if df.empty:
        return []
    return [SimpleNamespace(**row) for row in df.to_dict("records")]


def _auto_run_weekly(monday: str, uid) -> None:
    """Reuse a saved review if present; otherwise auto-generate + persist once."""
    err_key = f"_wk_err_{monday}"
    if st.session_state.get(err_key):
        return
    if get_weekly_review(monday, uid) is not None:
        return  # already saved — reuse, no API call
    if not _ai_on:
        return
    # The skeleton holds the note's geometry while the call runs, so the
    # page does not jump when the review lands.
    placeholder = st.empty()
    placeholder.markdown(render_note_skeleton(), unsafe_allow_html=True)
    try:
        review, _usage = generate_weekly_review(
            monday, user_id=uid, strategy_profile=_strategy
        )
        if not review["empty"]:
            save_weekly_review(review, overwrite=False, user_id=uid)
    except WeeklyReviewError as exc:
        # A domain error carries a message written for the trader.
        st.session_state[err_key] = str(exc)
    except Exception:  # noqa: BLE001 — never crash the page
        # Anything else is a driver, network or parser message that can
        # carry a DSN, a key or a fragment of the row: log it, do not
        # render it.
        _log.exception("weekly review failed for user %s week %s", uid, monday)
        st.session_state[err_key] = _AI_FAILED
    finally:
        placeholder.empty()


def _render_weekly_lens() -> None:
    picked = st.date_input(
        "Pick any day in the week to review",
        value=_default_week(df),
        key="ins_wk_pick",
    )
    monday, sunday = week_bounds(picked)

    # Below five complete trades a weekly recap mostly describes noise, so
    # it is not auto-generated: the trader is told what would unlock it.
    complete = activation_status(
        strategy=_strategy, trades=_trade_rows_for_activation(), weekly_review=None
    ).complete_trades

    if complete < TRADES_FOR_REVIEW and get_weekly_review(monday, uid) is None:
        st.markdown(
            render_empty_state(
                "rate_review",
                f"Journal {TRADES_FOR_REVIEW - complete} more completed trades",
                "A weekly review needs a sample it can say something true about.",
            ),
            unsafe_allow_html=True,
        )
        return

    _auto_run_weekly(monday, uid)
    existing = get_weekly_review(monday, uid)
    err = st.session_state.get(f"_wk_err_{monday}")

    if existing is not None:
        _note_stats(existing.get("stats") or {})
        _render_generated_note(
            existing,
            "Week in review",
            f"{monday} → {sunday}",
            key="_ins_weekly_section",
        )
        if _ai_on:
            busy_key = f"_wk_busy_{monday}"
            busy = bool(st.session_state.get(busy_key))
            clicked = st.button(
                "Regenerate this week",
                key="secondary_ins_wk_regen",
                disabled=busy,
            )
            if busy:
                _regenerating()
                st.session_state[busy_key] = False
                # The existing note stays on screen until a replacement
                # succeeds — a failed regeneration must not cost the review
                # the trader already had.
                try:
                    review, _usage = generate_weekly_review(
                        monday, user_id=uid, strategy_profile=_strategy
                    )
                    if review["empty"]:
                        st.caption("This week has nothing logged to review.")
                    else:
                        save_weekly_review(review, overwrite=True, user_id=uid)
                        st.session_state.pop(f"_wk_err_{monday}", None)
                        st.rerun()
                except WeeklyReviewError as exc:
                    _error_box(f"Could not regenerate: {exc}")
                except Exception:  # noqa: BLE001 — never crash the page
                    _log.exception("weekly regeneration failed for user %s", uid)
                    _error_box(_AI_FAILED)
            elif clicked:
                # Two passes on purpose. A Streamlit button cannot become
                # disabled during its own handler — the script run is
                # blocking, so the browser holds the live control for the
                # whole call. The click only records the intent; the next
                # pass renders the control disabled, says the review is
                # updating, and then makes the call.
                st.session_state[busy_key] = True
                st.rerun()
    elif err:
        _error_box(f"AI weekly review couldn't run: {err}")
        if st.button("Retry weekly review", key="secondary_ins_wk_retry"):
            st.session_state.pop(f"_wk_err_{monday}", None)
            st.rerun()
    else:
        st.caption("This week has nothing logged to review yet.")


# ══════════════════════════════════════════════════════════════════
# Lens 3 — Daily Debrief (on-demand, one completed trading day)
# ══════════════════════════════════════════════════════════════════
def _latest_trade_date(frame: pd.DataFrame) -> datetime.date:
    """Most recent trading day in the journal — the day worth debriefing."""
    try:
        latest = pd.to_datetime(frame["trade_date"], errors="coerce").max()
        if pd.notna(latest):
            return latest.date()
    except Exception:  # noqa: BLE001
        pass
    return datetime.date.today()


def _run_daily_debrief(day_iso: str, day_trades: list, cache_key: str) -> None:
    placeholder = st.empty()
    placeholder.markdown(render_note_skeleton(), unsafe_allow_html=True)
    try:
        review, usage = generate_debrief(
            day_trades,
            strategy_profile=_strategy,
            period_label=f"Trading day {day_iso}",
        )
        st.session_state[cache_key] = review
        # A successful run clears the reason the previous one failed; leaving
        # it set would print a stale error beside a fresh note.
        st.session_state.pop(cache_key + "_err", None)
        from src.tradelens.services.cost import log_ai_usage

        log_ai_usage("Daily Debrief", usage, user_id=uid)
    except DebriefError as exc:
        st.session_state[cache_key + "_err"] = str(exc)
    except Exception:  # noqa: BLE001 — never crash the page
        _log.exception("daily debrief failed for user %s day %s", uid, day_iso)
        st.session_state[cache_key + "_err"] = _AI_FAILED
    finally:
        placeholder.empty()


def _render_daily_lens() -> None:
    day = st.date_input(
        "Trading day to review", value=_latest_trade_date(df), key="ins_dbf_day"
    )
    day_iso = day.isoformat()
    cache_key = f"_dbf_{uid}_{day_iso}"
    day_trades = get_trades(start_date=day_iso, end_date=day_iso, user_id=uid)

    if not day_trades:
        st.caption("No trades logged on this day — pick a day you traded.")
        return
    if not _ai_on:
        st.info(
            "Add your Anthropic API key in Settings to generate a daily debrief. "
            "Your trades for the day are still listed in the Journal."
        )
        return

    err = st.session_state.get(cache_key + "_err")
    review = st.session_state.get(cache_key)
    if review is not None:
        _note_stats(review.get("stats") or {})
        _render_generated_note(
            review, "Day in review", day_iso, key="_ins_daily_section"
        )
        # A regeneration that failed leaves the note it could not replace on
        # screen, so its reason has to appear beside that note rather than in
        # the never-generated branch below, which this path never reaches.
        if err:
            _error_box(f"Could not regenerate: {err}")
        # A path back to the records the note is about.
        try:
            st.page_link(
                "pages/2_Trades.py", label="Open these trades in the Journal →"
            )
        except Exception:  # noqa: BLE001 — registry-less boots (AppTest) raise
            st.markdown(
                f'<a href="{escape(route_href("/Trades", st.query_params.get("auth")), quote=True)}"'
                ' target="_self">Open these trades in the Journal →</a>',
                unsafe_allow_html=True,
            )
        busy_key = cache_key + "_busy"
        busy = bool(st.session_state.get(busy_key))
        clicked = st.button(
            "Regenerate debrief", key="secondary_ins_dbf_regen", disabled=busy
        )
        if busy:
            _regenerating()
            st.session_state[busy_key] = False
            # The cached note is NOT cleared first. `_run_daily_debrief`
            # writes the replacement only on success, so popping the key
            # before the call meant a DebriefError destroyed the review the
            # trader already had — Weekly never did this, and said so.
            _run_daily_debrief(day_iso, day_trades, cache_key)
            st.rerun()
        elif clicked:
            # Two passes: a Streamlit button cannot become disabled during
            # its own blocking handler. See the weekly lens for the same
            # pattern and the same reason.
            st.session_state[busy_key] = True
            st.rerun()
    elif err:
        _error_box(f"Daily debrief couldn't run: {err}")
        if st.button("Retry debrief", key="secondary_ins_dbf_retry"):
            st.session_state.pop(cache_key + "_err", None)
            st.rerun()
    else:
        n = len(day_trades)
        plural = "s" if n != 1 else ""
        if st.button(
            f"Generate debrief for {day_iso} ({n} trade{plural})",
            type="primary",
            key="ins_dbf_run",
        ):
            _run_daily_debrief(day_iso, day_trades, cache_key)
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# Lens selector, then the active note
# ══════════════════════════════════════════════════════════════════
_LENS_BODIES = {
    "Patterns": _render_patterns_lens,
    "Weekly Recap": _render_weekly_lens,
    "Daily Debrief": _render_daily_lens,
}

# The lens lives in a plain key, separate from the selector's own widget
# key: Streamlit raises on any write to a widget's key after that widget
# is instantiated.
_default_lens = st.session_state.get(_LENS_KEY, AI_REVIEW_LENSES[0])
if _default_lens not in AI_REVIEW_LENSES:
    _default_lens = AI_REVIEW_LENSES[0]

lens = (
    st.radio(
        "AI review lens",
        AI_REVIEW_LENSES,
        index=AI_REVIEW_LENSES.index(_default_lens),
        horizontal=True,
        key=_LENS_WIDGET_KEY,
        label_visibility="collapsed",
    )
    or _default_lens
)
st.session_state[_LENS_KEY] = lens

st.markdown(render_section_header(lens, _LENS_QUESTIONS[lens]), unsafe_allow_html=True)
_LENS_BODIES[lens]()

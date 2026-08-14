from __future__ import annotations  # PEP 604 unions on the pinned Python 3.9

import sys
from pathlib import Path

# parents[3] of src/tradelens/ui/app.py  →  project root
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as _st_boot  # noqa: E402

from src.tradelens.db.init_db import bootstrap_if_local  # noqa: E402
from src.tradelens.db.session import DatabaseUnavailableError  # noqa: E402

# Bootstraps a LOCAL SQLite database only; a documented no-op against anything
# else. Deployed schemas belong to Alembic.
#
# This used to call init_db() unconditionally, on the assumption that Streamlit
# Cloud started from a fresh SQLite file each deploy. Production actually runs
# on Neon, so every restart ran create_all + _reconcile_columns against the real
# database — which is how production acquired a full schema with no
# alembic_version row, and how users.email arrived without its unique index
# (_reconcile_columns adds columns and never indexes). See db/init_db.py.
#
# Wrapped because this is the FIRST thing that touches the database, and an
# unhandled failure here is handled by Streamlit rather than by us — which
# means its own error view, a traceback, and the connection string printed
# into the browser. Measured with a deliberately unusable DATABASE_URL: the
# rendered page contained both `Traceback` and the DSN.
#
# `st.stop()` is what makes this fail closed. The script ends here; no page
# body runs, no service is called, no authentication path is entered, and
# nothing downgrades to a local file.
try:
    bootstrap_if_local()
except DatabaseUnavailableError:
    _st_boot.error("TradeLens is temporarily unavailable. Please try again shortly.")
    _st_boot.stop()
except Exception:  # noqa: BLE001 — same containment for any other DB failure
    # No `exc` binding on purpose: there is no branch here that could be
    # tempted to render or log it, and a driver's message carries the DSN.
    _st_boot.error("TradeLens is temporarily unavailable. Please try again shortly.")
    _st_boot.stop()
Path(__file__).resolve().parents[3].joinpath("data", "screenshots").mkdir(
    parents=True, exist_ok=True
)

import datetime  # noqa: E402
import math  # noqa: E402
from html import escape  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.tradelens.services.metrics import (  # noqa: E402
    compute_basic_metrics,
    compute_expectancy,
    compute_profit_factor_raw,
    current_week_pnl,
    compute_breakdown,
    daily_equity_curve,
    get_last_n_trades,
    today_pnl,
)
from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.sample_data import count_sample_trades  # noqa: E402
from src.tradelens.services.activation import activation_status  # noqa: E402
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.weekly import get_weekly_review, week_bounds  # noqa: E402
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
)
from src.tradelens.ui.components.charts import equity_curve_chart  # noqa: E402
from src.tradelens.ui.components.data_state import (  # noqa: E402
    MIN_DATED_POINTS,
    leading_category,
    render_data_state,
    sample_state,
    show_dated_instrument,
)
from src.tradelens.ui.components.overview_bands import (  # noqa: E402
    discipline_measures,
    next_review_action,
    ranked_rows,
    render_discipline_panel,
    render_flanking_figures,
    render_ranked_list,
    trajectory_figures,
)
from src.tradelens.ui.components.sidebar import (  # noqa: E402
    render_sidebar,
    route_href,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.strategy_gate import enforce_first_run  # noqa: E402
from src.tradelens.ui.components.trade_calendar import (  # noqa: E402
    render_trade_calendar,
)
from src.tradelens.ui.components.theme import (  # noqa: E402
    KILLZONE_LABELS,
    PLOTLY_TEMPLATE,
    inject_css,
)
from src.tradelens.ui.design_system import (  # noqa: E402
    get_asset_as_base64,
    inject_design_system,
    render_badge,
    render_empty_state,
    render_next_step,
    render_section_header,
)
from src.tradelens.ui.components.workspace import (  # noqa: E402
    EvidenceItem,
    MetricItem,
    render_editorial_readout,
    render_filter_summary,
    render_kpi_strip,
    render_workspace_header,
)

# Streamlit's page_link needs the file path; the slug is the fallback for
# registry-less boots (AppTest).
_NEXT_STEP_PAGES = {
    "strategy": "pages/5_Strategy.py",
    "first_trade": "pages/1_NewTrade.py",
    "weekly_review": "pages/6_Insights.py",
}

st.set_page_config(
    page_title="TradeLens AI",
    layout="wide",
    # "auto", not "expanded": on a phone an expanded sidebar covers the whole
    # dashboard, so the first thing a mobile visitor sees is navigation
    # instead of their trades. Auto keeps it open on desktop and collapsed
    # on small screens.
    initial_sidebar_state="auto",
)
inject_css()
inject_design_system()  # design_system.py wins ties (injected after theme)
require_auth()  # gate: shows the login page and halts here until signed in
uid = current_user_id()
# First run for a site-authenticated arrival goes to the Strategy Profile before
# the dashboard: every AI review on this page reads those rules, so a dashboard
# rendered before they exist is the weakest version of the product. Site path
# only — legacy sessions are untouched (see strategy_gate.enforce_first_run).
enforce_first_run(st, uid)
render_demo_banner()

_DF_COLS = [
    "id",
    "trade_date",
    "asset",
    "direction",
    "result",
    "pnl",
    "rr_realized",
    "setup_type",
    "ai_grade",
    "user_grade",
    "killzone",
    "followed_rules",
    "mistake_tags",
    "htf_bias",
    "updated_at",
]


def _load_df() -> pd.DataFrame:
    trades = get_trades(user_id=uid)
    df = pd.DataFrame([{c: getattr(t, c, None) for c in _DF_COLS} for t in trades])
    if df.empty:
        return df
    # Drop rows with no trade_date (legacy/empty rows would break date math).
    return df[df["trade_date"].notna() & (df["trade_date"] != "")].reset_index(
        drop=True
    )


_RESULT_VARIANT = {"Win": "success", "Loss": "danger"}  # else neutral (BE)


def _money(value) -> str:
    """Signed currency, or N/A. Never '--', never a bare 0 for missing."""
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    return f"{'-' if value < 0 else ''}${abs(value):,.2f}"


def _tone(value) -> str:
    """Semantic tone for a signed figure. Zero is neutral, not positive."""
    if value is None or pd.isna(value):
        return "neutral"
    value = float(value)
    return "positive" if value > 0 else "negative" if value < 0 else "neutral"


def _overview_metrics(df: pd.DataFrame) -> list:
    """The five headline measures of the ruled strip.

    One measurement across a period, so they share a strip rather than six
    boxes. Values arrive pre-formatted — the strip renders, it never rounds.
    """
    metrics = compute_basic_metrics(df)
    expectancy = compute_expectancy(metrics)
    profit_factor = compute_profit_factor_raw(df)
    if metrics["total_trades"] == 0 or (
        profit_factor == 0.0 and metrics["total_pnl"] == 0.0
    ):
        # 0/0 (no trades, or breakeven-only) is undefined — "N/A", not "0.0x".
        profit_factor = None

    if profit_factor is None:
        pf_text = "N/A"
    elif math.isinf(profit_factor):
        pf_text = "∞"
    else:
        pf_text = f"{profit_factor:.1f}x"

    wins = int(round(metrics["win_rate"] * metrics["total_trades"]))
    return [
        MetricItem(
            "Net P&L",
            _money(metrics["total_pnl"]),
            detail=f"{metrics['total_trades']} trades",
            tone=_tone(metrics["total_pnl"]),
        ),
        MetricItem(
            "Win rate",
            f"{metrics['win_rate'] * 100:.1f}%",
            detail=f"{wins} of {metrics['total_trades']}",
        ),
        MetricItem("Expectancy", _money(expectancy), tone=_tone(expectancy)),
        MetricItem("Profit factor", pf_text),
        MetricItem("Trades", f"{metrics['total_trades']:,}"),
    ]


def _overview_observation(df: pd.DataFrame) -> tuple | None:
    """One editorial reading of the period, or None when nothing is earned.

    The decision of what is true lives in ``data_state.leading_category``;
    this is only the wording. Grounded in figures already on the page —
    which session carried the period's P&L, over how many trades. It
    describes what the journal recorded and never suggests what to take next.
    """
    leader = leading_category(df, "killzone")
    if leader is None:
        return None

    label = KILLZONE_LABELS.get(leader.key, leader.key.replace("_", " ").title())
    plural = "trade" if leader.count == 1 else "trades"

    if leader.overall_total > 0 and leader.share >= 0.5:
        body = (
            f"{label} carried most of this period's result: "
            f"{_money(leader.total)} of {_money(leader.overall_total)} net, "
            f"across {leader.count} {plural}."
        )
    else:
        body = (
            f"{label} recorded the strongest net result this period at "
            f"{_money(leader.total)}, across {leader.count} {plural}."
        )

    return (
        "What this period recorded",
        body,
        EvidenceItem(
            evidence=f"{label} · {_money(leader.total)} net",
            sample=f"n={leader.count} of {len(df)}",
            confidence=(
                "high"
                if leader.count >= 12
                else "medium" if leader.count >= 6 else "low"
            ),
            limitation=(
                "Only one session is represented, so there is nothing to "
                "compare it against."
                if leader.is_only_category
                else None
            ),
        ),
    )


def _render_today_brief(df: pd.DataFrame) -> None:
    """Where the trader stands right now.

    Today's and this week's P&L left the headline strip — they answer a
    different question from "how is my process doing", and mixing the two
    is what made the old six-card row read as noise.
    """
    today = today_pnl(df)
    week = current_week_pnl(df)
    st.markdown(
        render_kpi_strip(
            [
                MetricItem("Today", _money(today), tone=_tone(today)),
                MetricItem("This week", _money(week), tone=_tone(week)),
            ]
        ),
        unsafe_allow_html=True,
    )


def _render_recent_trades(recent: pd.DataFrame) -> None:
    """The last ten trades as a quiet ledger."""
    if recent.empty:
        st.markdown(
            render_empty_state(
                "menu_book",
                "No trades to show",
                "Your latest trades will appear here.",
                image_path="empty_trades.png",
            ),
            unsafe_allow_html=True,
        )
        return
    st.markdown(_recent_table(recent), unsafe_allow_html=True)


def _recent_table(recent: pd.DataFrame) -> str:
    """Pure HTML for the Recent Trades table (rendering only, all text escaped)."""
    head = (
        "<tr><th>Date</th><th>Asset</th><th>Session</th><th>Setup</th>"
        '<th>Result</th><th class="num">P&amp;L</th>'
        '<th class="num">R Multiple</th></tr>'
    )
    rows = []
    for r in recent.to_dict("records"):
        result = str(r.get("result") or "—")
        badge = render_badge(result, _RESULT_VARIANT.get(result, "neutral"))
        pnl = r.get("pnl")
        if pd.isna(pnl):
            pnl_cls, pnl_txt = "mono", "N/A"
        else:
            sign = "-" if pnl < 0 else ""
            pnl_txt = f"{sign}${abs(pnl):,.2f}"
            pnl_cls = (
                "mono pnl-pos" if pnl > 0 else "mono pnl-neg" if pnl < 0 else "mono"
            )
        rr = r.get("rr_realized")
        rr_txt = "N/A" if pd.isna(rr) else f"{float(rr):.1f}R"
        session = KILLZONE_LABELS.get(str(r.get("killzone") or ""), "—")
        rows.append(
            "<tr>"
            f'<td class="mono">{escape(str(r.get("trade_date") or "—"))}</td>'
            f'<td>{escape(str(r.get("asset") or "—"))}</td>'
            f"<td>{escape(session)}</td>"
            f'<td>{escape(str(r.get("setup_type") or "—"))}</td>'
            f"<td>{badge}</td>"
            f'<td class="{pnl_cls} num">{pnl_txt}</td>'
            f'<td class="mono num">{rr_txt}</td>'
            "</tr>"
        )
    return (
        '<div class="tl-table-wrap"><table class="tl-table">'
        f"<thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


# ── Load data ─────────────────────────────────────────────────────
df = _load_df()

# DEMO_MODE on a cold/empty DB: show rich synthetic data so the app is alive.
if df.empty and is_demo():
    df = get_demo_df()

render_sidebar()

# ── Page masthead: what this is, whose rules, and over what period ─
_strategy = get_active_strategy(uid) if uid is not None else None
_strategy_name = (_strategy or {}).get("name")
_sample_active = count_sample_trades(uid) > 0

# Demo state is labelled ONCE, in the masthead eyebrow, instead of repeating
# as a full-width banner above the numbers it describes (spec 11.1).
_eyebrow_bits = []
if _sample_active:
    _eyebrow_bits.append("Sample data")
if _strategy_name:
    _eyebrow_bits.append(_strategy_name)
_eyebrow = " · ".join(_eyebrow_bits) or None

_dates = df["trade_date"].dropna().astype(str) if not df.empty else pd.Series(dtype=str)
_range = f"{_dates.min()} → {_dates.max()}" if not _dates.empty else None

st.markdown(
    render_workspace_header(
        "Overview",
        "Where the week stands, and what deserves review next.",
        eyebrow=_eyebrow,
        meta=_range,
    ),
    unsafe_allow_html=True,
)

# ── Empty state (0 trades): full-page welcome ─────────────────────
if df.empty:
    _welcome_b64 = get_asset_as_base64("welcome.png")
    _cta_b64 = get_asset_as_base64("cta_log_trade.png")
    _auth_token = st.query_params.get("auth")
    _new_trade_href = escape(route_href("/NewTrade", _auth_token), quote=True)
    _settings_href = escape(route_href("/Settings", _auth_token), quote=True)
    _parts = ['<div class="tl-empty-state tl-welcome">']
    if _welcome_b64:
        _parts.append(
            '<img class="tl-welcome-img" alt="Welcome to TradeLens AI" '
            f'src="data:image/png;base64,{_welcome_b64}" />'
        )
    _parts.append('<h2 class="tl-welcome-title">Welcome to TradeLens AI</h2>')
    _parts.append('<p class="tl-welcome-sub">Your AI-powered post-trade journal.</p>')
    if _cta_b64:
        _parts.append(
            '<img class="tl-welcome-cta-img" alt="" '
            f'src="data:image/png;base64,{_cta_b64}" />'
        )
    _parts.append(
        f'<a class="tl-empty-action" href="{_new_trade_href}" target="_self">'
        "Log Your First Trade →</a><br/>"
        f'<a class="tl-empty-action" href="{_settings_href}" target="_self">'
        "Load sample trades</a>"
    )
    _parts.append("</div>")
    st.markdown("".join(_parts), unsafe_allow_html=True)
    st.stop()

# ── Asset filter — compact, and scoping every figure below ────────
# Options come from the trader's actual history, never a static list. The
# control stays available but collapses into a summary line once used, so
# it does not read as a second panel above the numbers.
_traded_assets = sorted({str(a) for a in df["asset"].dropna() if str(a).strip()})
with st.expander("Filter", expanded=False):
    asset_choice = st.selectbox(
        "Asset", ["All assets", *_traded_assets], key="dash_asset"
    )
if asset_choice != "All assets":
    df = df[df["asset"].astype(str) == asset_choice].reset_index(drop=True)

st.markdown(
    render_filter_summary(
        [("Asset", asset_choice)] if asset_choice != "All assets" else []
    ),
    unsafe_allow_html=True,
)

# Filtered to empty. The 0-trade welcome above runs BEFORE the filter, so
# without this a scope that matches nothing rendered band 1 as a strip of
# zeros — figures that look like a flat account rather than an empty scope.
# Suppress the bands, say what the scope is, and offer the way back.
if df.empty:
    st.markdown(
        render_empty_state(
            "filter_alt",
            f"No trades for {asset_choice}",
            "That is the filter, not the account. Clear it to see everything "
            "you have logged.",
        ),
        unsafe_allow_html=True,
    )
    if st.button("Show all assets", key="secondary_dash_clear_filter"):
        st.session_state["dash_asset"] = "All assets"
        st.rerun()
    st.stop()

# ── Band 1: current standing. One ruled KPI strip, not six cards ──
st.markdown(render_kpi_strip(_overview_metrics(df)), unsafe_allow_html=True)

# Today / this week demote to a quieter second strip inside band 1 — they
# answer a different question from the five headline measures above.
if not df.empty:
    _render_today_brief(df)

# ── Band 2: can this standing be trusted? ─────────────────────────
# A different FORM from band 1 on purpose — figure above sample, one ruled
# panel. Five bands, five forms is what keeps the Overview an argument
# rather than a wall of equal cards (spec 5.1). Only shown once there is a
# trade to be disciplined about.
if not df.empty:
    st.markdown(
        render_section_header(
            "Risk and discipline",
            "Whether the numbers above describe a process or a run of luck.",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(
        render_discipline_panel(discipline_measures(df)), unsafe_allow_html=True
    )

# Activation is computed here but RENDERED in band 5 at the foot of the page:
# the reading order is standing → trust → trajectory → what repeats → what to
# do about it, and the action belongs at the end of that argument, not before
# the trader has seen any of it.
_activation = None
if uid is not None:
    _activation = activation_status(
        strategy=_strategy,
        trades=get_trades(user_id=uid),
        weekly_review=get_weekly_review(week_bounds(datetime.date.today())[0], uid),
    )

# ── The composed panel: standing on the left, trajectory on the right
# Two columns, deliberately unequal. The chart is the dominant instrument;
# the brief and calendar are the context you read it against.
_state = sample_state(df)

# ── Band 3: how did this standing come about? ─────────────────────
# The dominant instrument on the page, flanked by figures that describe the
# SHAPE of the sequence rather than restating band 1's totals. A third form
# again — chart plus a quiet stack, not a strip and not a panel.
if not df.empty:
    st.markdown(
        render_section_header(
            "Performance trajectory",
            "The path the account took to get here.",
        ),
        unsafe_allow_html=True,
    )
    _chart_col, _flank_col = st.columns([2.4, 1], gap="large")

    with _chart_col:
        eq = daily_equity_curve(df)
        if not show_dated_instrument(_state):
            # Below four populated trading days there is no shape to read, and
            # a dominant chart drawn through two dots claims a trend the sample
            # has not earned. State the standing and say what unlocks it.
            _needed = max(0, MIN_DATED_POINTS - _state.dated_points)
            render_data_state(
                "Not enough dated trades for a curve",
                f"{_needed} more trading "
                f"{'day' if _needed == 1 else 'days'} will unlock the equity "
                "curve. The figures above already reflect every trade logged.",
                "show_chart",
            )
        elif not eq.empty:
            fig = equity_curve_chart(eq)
            fig.update_layout(
                template=PLOTLY_TEMPLATE,
                height=360,
                margin=dict(l=8, r=8, t=8, b=8),
            )
            _day_counts = df.groupby("trade_date").size()
            fig.update_traces(
                customdata=eq["trade_date"].map(_day_counts).fillna(0).astype(int),
                hovertemplate=(
                    "%{x}<br>Cumulative P&L: $%{y:,.2f}"
                    "<br>Trades: %{customdata}<extra></extra>"
                ),
            )
            with st.container(border=True):
                # theme=None keeps the TradeLens template's chart stage; the
                # default repaints the figure in Streamlit's own theme.
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    theme=None,
                    config={"displayModeBar": False},
                )
        else:
            st.markdown(
                render_empty_state(
                    "show_chart",
                    "No equity data yet",
                    "Log trades to build your equity curve.",
                ),
                unsafe_allow_html=True,
            )

    with _flank_col:
        st.markdown(
            render_flanking_figures(trajectory_figures(df)), unsafe_allow_html=True
        )

# ── Band 4: what keeps repeating? ─────────────────────────────────
# Ranked lists, not pie charts: a trader comparing session P&L reads
# magnitudes, not silhouettes. Nothing may be called strongest while only one
# category is present — leading_category owns that decision.
if not df.empty:
    st.markdown(
        render_section_header(
            "Recurring edge",
            "Where the account repeats itself, and how large the sample is.",
        ),
        unsafe_allow_html=True,
    )
    _session_col, _setup_col = st.columns(2, gap="large")

    with _session_col:
        # compute_breakdown, not by_session/by_setup_type: those are documented
        # as outcome-composition helpers with no P&L column, and the spec
        # ranks these lists by net P&L. compute_breakdown returns exactly
        # that, already sorted, for any column.
        # "killzone" is what this product records — there is no `session`
        # column on the Overview frame, and the spec names killzone_performance
        # as the alternative for exactly this reason. Labels come from the same
        # map the ledger uses so one dimension does not get two vocabularies.
        _session_rows = ranked_rows(
            compute_breakdown(df, "killzone"),
            label_column="killzone",
            labels=KILLZONE_LABELS,
        )
        _session_lead = leading_category(df, "killzone")
        st.markdown(
            render_ranked_list(
                "Killzone performance",
                _session_rows,
                rankable=bool(_session_lead) and not _session_lead.is_only_category,
            )
            or render_empty_state(
                "schedule",
                "No killzone data yet",
                "Tag a killzone on completed trades to compare recurring windows.",
            ),
            unsafe_allow_html=True,
        )

    with _setup_col:
        _setup_rows = ranked_rows(
            compute_breakdown(df, "setup_type"), label_column="setup_type"
        )
        _setup_lead = leading_category(df, "setup_type")
        st.markdown(
            render_ranked_list(
                "Setup performance",
                _setup_rows,
                rankable=bool(_setup_lead) and not _setup_lead.is_only_category,
            )
            or render_empty_state(
                "extension",
                "No setup data yet",
                "Record a setup type to see which ones repeat.",
            ),
            unsafe_allow_html=True,
        )

    st.markdown(render_section_header("Trading days"), unsafe_allow_html=True)
    render_trade_calendar(df, compact=True)
    st.page_link("pages/2_Trades.py", label="Open the full journal →")

# ── Band 5: what do I do about it? ────────────────────────────────
# One editorial readout and exactly one link. Absorbs the activation card and
# the period observation into a single band: which one appears is a state
# question, decided in overview_bands, and the band is omitted entirely when
# neither is earned — an empty band is worse than no band (spec 5.6).
_band5 = next_review_action(df, _activation)
if _band5 is not None:
    st.markdown(
        render_section_header(
            "Next review action", "What to go and re-read, not what to trade."
        ),
        unsafe_allow_html=True,
    )
    if _band5.kind == "next_step":
        st.markdown(
            render_next_step(
                _band5.title,
                _activation.completed,
                _activation.total,
                (
                    _activation.trades_until_review
                    if _activation.next_key == "weekly_review"
                    else 0
                ),
            ),
            unsafe_allow_html=True,
        )
        try:
            st.page_link(
                _NEXT_STEP_PAGES[_activation.next_key],
                label=f"{_band5.link_label} →",
            )
        except Exception:  # noqa: BLE001 — registry-less boots (AppTest) raise
            st.markdown(
                f'<a href="{escape(str(_band5.link_slug))}" target="_self">'
                f"{escape(str(_band5.link_label))} →</a>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            render_editorial_readout(_band5.title, _band5.body, _band5.evidence),
            unsafe_allow_html=True,
        )

_rt_head, _rt_link = st.columns([5, 1], vertical_alignment="bottom")
_rt_head.markdown(render_section_header("Recent trades"), unsafe_allow_html=True)
_rt_link.page_link("pages/2_Trades.py", label="View all →")
_render_recent_trades(get_last_n_trades(df, 10))

from __future__ import annotations  # PEP 604 unions on the pinned Python 3.9

import sys
from pathlib import Path

# parents[3] of src/tradelens/ui/app.py  →  project root
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.tradelens.db.init_db import init_db  # noqa: E402

# Idempotent: creates tables on first run, no-op if already exist.
# Required on Streamlit Cloud where SQLite starts fresh on each deploy.
init_db()
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
    daily_equity_curve,
    get_last_n_trades,
    today_pnl,
)
from src.tradelens.services.demo import get_demo_df, is_demo  # noqa: E402
from src.tradelens.services.sample_data import count_sample_trades  # noqa: E402
from src.tradelens.services.activation import (  # noqa: E402
    NEXT_STEP_COPY,
    activation_status,
)
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.weekly import get_weekly_review, week_bounds  # noqa: E402
from src.tradelens.ui.components.auth import (  # noqa: E402
    current_user_id,
    require_auth,
)
from src.tradelens.ui.components.charts import equity_curve_chart  # noqa: E402
from src.tradelens.ui.components.data_state import (  # noqa: E402
    leading_category,
    render_data_state,
    sample_state,
)
from src.tradelens.ui.components.sidebar import (  # noqa: E402
    render_sidebar,
    route_href,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
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

# ── One ruled KPI strip — not six separate cards ──────────────────
st.markdown(render_kpi_strip(_overview_metrics(df)), unsafe_allow_html=True)

# ── Next step, while the trader is still getting to first value ───
# One action, not a checklist, and only until they've had a real review.
if uid is not None:
    _activation = activation_status(
        strategy=_strategy,
        trades=get_trades(user_id=uid),
        weekly_review=get_weekly_review(week_bounds(datetime.date.today())[0], uid),
    )
    if not _activation.is_activated and _activation.next_key:
        _label, _target, _link = NEXT_STEP_COPY[_activation.next_key]
        st.markdown(
            render_next_step(
                _label,
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
            st.page_link(_NEXT_STEP_PAGES[_activation.next_key], label=f"{_link} →")
        except Exception:  # noqa: BLE001 — registry-less boots (AppTest) raise
            st.markdown(
                f'<a href="{_target}" target="_self">{escape(_link)} →</a>',
                unsafe_allow_html=True,
            )

# ── The composed panel: standing on the left, trajectory on the right
# Two columns, deliberately unequal. The chart is the dominant instrument;
# the brief and calendar are the context you read it against.
_state = sample_state(df)
_brief_col, _chart_col = st.columns([1, 1.6], gap="large")

with _brief_col:
    # "Where you stand", not "Today": the cells below are already labelled
    # TODAY and THIS WEEK, and a heading that repeats its own first cell is
    # chrome, not structure.
    st.markdown(render_section_header("Where you stand"), unsafe_allow_html=True)
    _render_today_brief(df)
    st.markdown(render_section_header("Trading days"), unsafe_allow_html=True)
    render_trade_calendar(df, compact=True)
    st.page_link("pages/2_Trades.py", label="Open the full journal →")

with _chart_col:
    st.markdown(render_section_header("Equity curve"), unsafe_allow_html=True)
    eq = daily_equity_curve(df)
    if not _state.show_dominant_series:
        # Below four dated points there is no shape to read, and a dominant
        # chart drawn through two dots claims a trend the sample has not
        # earned. State the standing instead, and say what unlocks the curve.
        _needed = max(0, 4 - _state.dated_points)
        render_data_state(
            "Not enough dated trades for a curve",
            f"{_needed} more trading "
            f"{'day' if _needed == 1 else 'days'} will unlock the equity curve. "
            "The figures above already reflect every trade logged.",
            "show_chart",
        )
    elif not eq.empty:
        fig = equity_curve_chart(eq)
        # Colors/grid/fonts come from the shared template (plotly default);
        # only size and margins are page-specific.
        fig.update_layout(
            template=PLOTLY_TEMPLATE,
            height=360,
            margin=dict(l=8, r=8, t=8, b=8),
        )
        # Hover: date, cumulative P&L, and how many trades that day.
        _day_counts = df.groupby("trade_date").size()
        fig.update_traces(
            customdata=eq["trade_date"].map(_day_counts).fillna(0).astype(int),
            hovertemplate=(
                "%{x}<br>Cumulative P&L: $%{y:,.2f}"
                "<br>Trades: %{customdata}<extra></extra>"
            ),
        )
        with st.container(border=True):
            # plotly_chart has no width= on streamlit 1.50 — use_container_width
            # stays here until the pin bumps (unlike buttons/images/dataframes).
            # theme=None keeps the TradeLens template's dark chart stage; the
            # default theme="streamlit" repaints the figure in the app's own
            # (now light) theme, which put bright teal marks on near-white.
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

    # One editorial reading of the period, with its own evidence.
    _observation = _overview_observation(df)
    if _observation:
        _title, _body, _evidence = _observation
        st.markdown(
            render_editorial_readout(_title, _body, _evidence),
            unsafe_allow_html=True,
        )


# ── Recent trades — a quiet ledger beneath the primary panel ──────
# bottom alignment: the section header carries a top margin the bare link
# does not, so a default top-aligned row leaves the link floating above the
# heading it belongs to.
_rt_head, _rt_link = st.columns([5, 1], vertical_alignment="bottom")
_rt_head.markdown(render_section_header("Recent trades"), unsafe_allow_html=True)
_rt_link.page_link("pages/2_Trades.py", label="View all →")
_render_recent_trades(get_last_n_trades(df, 10))

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
    render_data_state,
    sample_state,
)
from src.tradelens.ui.components.sidebar import render_sidebar  # noqa: E402
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
    render_banner,
    render_empty_state,
    render_kpi_card,
    render_next_step,
    render_section_header,
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
    initial_sidebar_state="expanded",
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

# ── Header: title + active-strategy badge + subtitle ──────────────
_strategy = get_active_strategy(uid) if uid is not None else None
_strategy_badge = (
    render_badge(_strategy["name"], "primary")
    if _strategy and _strategy.get("name")
    else ""
)
st.markdown(
    '<div class="tl-section-header">'
    '<div class="tl-chip-row">'
    '<span class="tl-section-title">Dashboard</span>'
    f"{_strategy_badge}"
    "</div>"
    '<div class="tl-section-subtitle">'
    "Your trading performance at a glance</div>"
    "</div>",
    unsafe_allow_html=True,
)

if count_sample_trades(uid) > 0:
    st.markdown(
        render_banner("Demo data active — these are sample trades.", "info"),
        unsafe_allow_html=True,
    )

# ── Empty state (0 trades): full-page welcome ─────────────────────
if df.empty:
    _welcome_b64 = get_asset_as_base64("welcome.png")
    _cta_b64 = get_asset_as_base64("cta_log_trade.png")
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
        '<a class="tl-empty-action" href="/NewTrade" target="_self">'
        "Log Your First Trade →</a><br/>"
        '<a class="tl-empty-action" href="/Settings" target="_self">'
        "Load sample trades</a>"
    )
    _parts.append("</div>")
    st.markdown("".join(_parts), unsafe_allow_html=True)
    st.stop()

# ── Asset filter (Item 12) — scopes every stat and chart below ────
# Options come from the trader's actual history, never a static list.
_traded_assets = sorted({str(a) for a in df["asset"].dropna() if str(a).strip()})
_fcol, _ = st.columns([1, 3])
asset_choice = _fcol.selectbox(
    "Asset filter", ["All assets", *_traded_assets], key="dash_asset"
)
if asset_choice != "All assets":
    df = df[df["asset"].astype(str) == asset_choice].reset_index(drop=True)

m = compute_basic_metrics(df)
t_pnl = today_pnl(df)
w_pnl = current_week_pnl(df)
exp = compute_expectancy(m)
pf_raw = compute_profit_factor_raw(df)  # inf → "∞" via ratio format
if m["total_trades"] == 0 or (pf_raw == 0.0 and m["total_pnl"] == 0.0):
    # 0/0 (no trades or breakeven-only) is undefined — "N/A", not "0.0x".
    pf_raw = None

# ── Row 1: KPI hero row (hero_bg + 0.65 overlay, 6 cards) ─────────
# One HTML flex row instead of st.columns(6): the hero background must
# wrap all six cards, and st.columns children can't share a styled div.
_hero_b64 = get_asset_as_base64("hero_bg.png")
_hero_style = (
    "background-image: linear-gradient(rgba(13,15,17,0.65), "
    f"rgba(13,15,17,0.65)), url(data:image/png;base64,{_hero_b64});"
    if _hero_b64
    else ""
)
_kpi_cards = "".join(
    [
        render_kpi_card("Today's P&L", t_pnl),
        render_kpi_card("This Week's P&L", w_pnl),
        render_kpi_card("Win Rate", m["win_rate"] * 100, format="percent"),
        render_kpi_card("Total Trades", m["total_trades"], format="number"),
        render_kpi_card("Profit Factor", pf_raw, format="ratio"),
        render_kpi_card("Expectancy", exp),
    ]
)
st.markdown(
    f'<div class="tl-hero-wrap" style="{_hero_style}">'
    f'<div class="tl-kpi-row">{_kpi_cards}</div></div>',
    unsafe_allow_html=True,
)

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

# ── Trading calendar (Item 12) — month view below the KPIs ────────
st.markdown(render_section_header("Trading Calendar"), unsafe_allow_html=True)
render_trade_calendar(df)


# ── Row 2: Equity curve (full width) ──────────────────────────────
st.markdown(render_section_header("Equity Curve"), unsafe_allow_html=True)
eq = daily_equity_curve(df)
_state = sample_state(df)
if not _state.show_series:
    # A "curve" through one dated point is a dot on an axis — the chart
    # canvas would imply a trend the sample cannot support.
    render_data_state(
        "Add one more dated trade",
        "Two trading dates are needed to draw a meaningful curve.",
        "📈",
    )
elif not eq.empty:
    fig = equity_curve_chart(eq)
    # Colors/grid/fonts come from the shared template (plotly default);
    # only size and margins are page-specific.
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=320,
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
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.markdown(
        render_empty_state(
            "📈", "No equity data yet", "Log trades to build your equity curve."
        ),
        unsafe_allow_html=True,
    )


# ── Row 3: Recent trades (last 10) ────────────────────────────────
_rt_head, _rt_link = st.columns([5, 1])
_rt_head.markdown(render_section_header("Recent Trades"), unsafe_allow_html=True)
_rt_link.page_link("pages/2_Trades.py", label="View All →")
recent = get_last_n_trades(df, 10)
if recent.empty:
    st.markdown(
        render_empty_state(
            "📓",
            "No trades to show",
            "Your latest trades will appear here.",
            image_path="empty_trades.png",
        ),
        unsafe_allow_html=True,
    )
else:
    st.markdown(_recent_table(recent), unsafe_allow_html=True)


# ── Row 4: Quick actions ──────────────────────────────────────────
st.markdown(render_section_header("Quick Actions"), unsafe_allow_html=True)
_ACTIONS = [
    ("📝", "Log Trade", "Capture today's execution while it's fresh", "/NewTrade"),
    ("📖", "Open Journal", "Revisit and reflect on past trades", "/Trades"),
    ("📊", "View Analytics", "Study your performance by setup", "/Analytics"),
]
# Inner elements are spans (styled display:block) — block tags inside an
# inline <a> get re-parsed by the markdown renderer and break the card.
for _col, (_icon, _title, _sub, _href) in zip(st.columns(3), _ACTIONS):
    _col.markdown(
        f'<a class="tl-action-link" href="{_href}" target="_self">'
        '<span class="tl-action-card">'
        f'<span class="tl-action-title">{_icon} {escape(_title)}</span>'
        f'<span class="tl-action-sub">{escape(_sub)}</span>'
        '<span class="tl-action-go">Go →</span>'
        "</span></a>",
        unsafe_allow_html=True,
    )

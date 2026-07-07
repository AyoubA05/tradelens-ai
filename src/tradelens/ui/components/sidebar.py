"""
Sidebar for TradeLens AI (Session A).

Renders the brand block, the custom navigation menu (exactly six destinations
with clean labels), an active-strategy badge, and the sign-out control. The
default Streamlit page nav is disabled via `.streamlit/config.toml`
(showSidebarNavigation = false) so this is the single source of navigation.

RENDER-ONLY: every value comes from a service; no DB queries or business logic.
"""

from __future__ import annotations

from src.tradelens.ui.components.theme import (
    TEAL,
    TERRA,
    TEXT_MUTED,
)

# Custom nav: (page path relative to the entrypoint, URL slug, label, Material
# icon). Paths/slugs keep the existing files — only the labels are friendly.
_NAV = [
    ("app.py", "/", "Dashboard", ":material/dashboard:"),
    ("pages/1_NewTrade.py", "/NewTrade", "New Trade", ":material/add_chart:"),
    ("pages/2_Trades.py", "/Trades", "Journal", ":material/menu_book:"),
    ("pages/4_Analytics.py", "/Analytics", "Analytics", ":material/analytics:"),
    (
        "pages/6_Insights.py",
        "/Insights",
        "Insights & Review",
        ":material/psychology:",
    ),
    ("pages/5_Strategy.py", "/Strategy", "Strategy Profile", ":material/flag:"),
    ("pages/9_Settings.py", "/Settings", "Settings", ":material/settings:"),
]


def _nav_link(st, path: str, slug: str, label: str, icon: str) -> None:
    """Render one soft-nav link. page_link does in-session navigation (the login
    state survives). It needs the multipage registry, which AppTest standalone
    boots don't build — there we degrade to a plain slug link so tests still boot.
    """
    try:
        st.page_link(path, label=label, icon=icon)
    except Exception:  # noqa: BLE001 — only triggers in registry-less boots/tests
        st.markdown(
            f'<a href="{slug}" target="_self" '
            'style="display:block;padding:4px 0">{}</a>'.format(label),
            unsafe_allow_html=True,
        )


_WORDMARK_SVG = (
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
    f'stroke="{TEAL}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" style="vertical-align:middle">'
    '<path d="M3 17 l5 -6 l4 3 l6 -8"/><path d="M3 21 h18"/></svg>'
)


def _brand_html() -> str:
    return (
        '<div style="margin-bottom:10px">'
        '<div style="display:flex;align-items:center;gap:8px">'
        f"{_WORDMARK_SVG}"
        "<span style=\"font-family:'Space Grotesk',sans-serif;font-weight:700;"
        'font-size:1.15rem;letter-spacing:-0.01em">TradeLens AI</span></div>'
        f'<div style="color:{TEXT_MUTED};font-size:0.75rem;margin-left:28px">'
        "Post-Trade Journal</div></div>"
    )


def _strategy_badge_html(strategy_name: str | None) -> str:
    if strategy_name:
        return (
            f'<div style="background:rgba(32,128,141,0.12);border:1px solid {TEAL};'
            "border-radius:8px;padding:8px 10px;margin:6px 0;font-size:0.8rem;"
            f'color:{TEAL}">🎯 Active Strategy: '
            f"<strong>{strategy_name}</strong></div>"
        )
    return (
        f'<div style="background:rgba(168,75,47,0.12);border:1px solid {TERRA};'
        "border-radius:8px;padding:8px 10px;margin:6px 0;font-size:0.8rem;"
        f'color:{TERRA}">No active strategy. Add one in Strategy Profile.</div>'
    )


def render_sidebar(df=None, today=None) -> None:
    """Render brand, navigation, active-strategy badge, and sign-out in the sidebar.

    `df` / `today` are accepted for backward compatibility but unused — the sidebar
    no longer shows per-period stats, keeping navigation the focus.
    """
    import streamlit as st

    from src.tradelens.services.strategy import get_active_strategy
    from src.tradelens.ui.components.auth import current_user, render_logout_button

    strategy = get_active_strategy()
    strategy_name = (strategy or {}).get("name")

    with st.sidebar:
        st.markdown(_brand_html(), unsafe_allow_html=True)

        for path, slug, label, icon in _NAV:
            _nav_link(st, path, slug, label, icon)

        st.markdown(_strategy_badge_html(strategy_name), unsafe_allow_html=True)

        st.divider()
        uname = current_user()
        if uname:
            st.caption(f"Signed in as: **{uname}**")
        render_logout_button()

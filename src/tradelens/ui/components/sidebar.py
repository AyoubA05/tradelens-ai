"""
Sidebar for TradeLens AI (Session A).

Renders the brand block, the custom navigation menu (exactly six destinations
with clean labels), an active-strategy badge, and the sign-out control. The
default Streamlit page nav is disabled via `.streamlit/config.toml`
(showSidebarNavigation = false) so this is the single source of navigation.

RENDER-ONLY: every value comes from a service; no DB queries or business logic.
"""

from __future__ import annotations

from html import escape

from src.tradelens.ui.design_system import TL_PRIMARY

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
    f'stroke="{TL_PRIMARY}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" style="vertical-align:middle">'
    '<path d="M3 17 l5 -6 l4 3 l6 -8"/><path d="M3 21 h18"/></svg>'
)


def _brand_html(logo_b64: str = "") -> str:
    mark = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="" width="20" height="20" '
        'style="border-radius:5px;vertical-align:middle;display:inline-block" />'
        if logo_b64
        else _WORDMARK_SVG
    )
    return (
        '<div class="tl-side-brand">'
        f"{mark}"
        '<span class="tl-side-brand-name">TradeLens AI</span></div>'
        '<div class="tl-side-brand-sub">Post-Trade Journal</div>'
    )


def _strategy_badge_html(strategy_name: str | None) -> str:
    if strategy_name:
        return (
            '<div class="tl-side-note active">Active strategy: '
            f"<b>{escape(strategy_name)}</b></div>"
        )
    return (
        '<div class="tl-side-note">No active strategy. '
        "Add one in Strategy Profile.</div>"
    )


def render_sidebar(df=None, today=None) -> None:
    """Render brand, navigation, active-strategy badge, and sign-out in the sidebar.

    `df` / `today` are accepted for backward compatibility but unused — the sidebar
    no longer shows per-period stats, keeping navigation the focus.
    """
    import streamlit as st

    from src.tradelens.services.strategy import get_active_strategy
    from src.tradelens.ui.components.auth import current_user, render_logout_button
    from src.tradelens.ui.design_system import get_asset_as_base64

    strategy = get_active_strategy()
    strategy_name = (strategy or {}).get("name")

    with st.sidebar:
        st.markdown(
            _brand_html(get_asset_as_base64("logo_mark.png")), unsafe_allow_html=True
        )

        for path, slug, label, icon in _NAV:
            _nav_link(st, path, slug, label, icon)

        st.markdown(_strategy_badge_html(strategy_name), unsafe_allow_html=True)

        st.divider()
        uname = current_user()
        if uname:
            st.caption(f"Signed in as: **{uname}**")
        render_logout_button()

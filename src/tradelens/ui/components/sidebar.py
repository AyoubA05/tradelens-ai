"""
App shell and navigation architecture for TradeLens AI.

The shell is the only UI present on every destination, so it carries the
product's information architecture:

- FIVE primary destinations — Overview, Journal, Analytics, AI Reviews and
  Strategy Profile — in the order a trader works through them.
- ONE persistent action, "Log completed trade". Logging is the thing a
  trader comes here to do; it is a button above the list, not a sixth peer
  of the places they browse.
- A quiet utility group (Settings, identity, sign out) below a divider.
- A separate five-item mobile hierarchy, because the desktop rail shrunk
  down is not a mobile navigation.

Renaming is presentational only. Dashboard reads as Overview and Insights &
Review as AI Reviews, but no page file moves and no URL slug changes — a
slug is a bookmark somebody already has.

The default Streamlit page nav is disabled via `.streamlit/config.toml`
(showSidebarNavigation = false) so this is the single source of navigation.

RENDER-ONLY: every value comes from a service; no DB queries or business logic.
"""

from __future__ import annotations

from html import escape
from urllib.parse import urlencode, urlparse

from src.tradelens.ui.design_system import TL_PRIMARY

# (page path relative to the entrypoint, URL slug, label, Material icon).
# Paths and slugs keep the existing files — only the labels are friendly.
PRIMARY_NAV = (
    ("app.py", "/", "Overview", ":material/space_dashboard:"),
    ("pages/2_Trades.py", "/Trades", "Journal", ":material/menu_book:"),
    ("pages/4_Analytics.py", "/Analytics", "Analytics", ":material/analytics:"),
    ("pages/6_Insights.py", "/Insights", "AI Reviews", ":material/psychology:"),
    ("pages/5_Strategy.py", "/Strategy", "Strategy Profile", ":material/flag:"),
)

# The one action, promoted out of the destination list.
PRIMARY_ACTION = (
    "pages/1_NewTrade.py",
    "/NewTrade",
    "Log completed trade",
    ":material/add_chart:",
)

# Present, reachable, and deliberately quiet.
UTILITY_NAV = (("pages/9_Settings.py", "/Settings", "Settings", ":material/settings:"),)

# Mobile bottom navigation: (slug, short label, Material icon name).
# The four journeys a trader repeats on a phone (spec 13) take the first
# four slots; the fifth is More.
MOBILE_NAV = (
    ("/", "Home", "space_dashboard"),
    ("/NewTrade", "Log", "add_chart"),
    ("/Trades", "Journal", "menu_book"),
    ("/Insights", "Review", "psychology"),
)

# What More opens. These are real destinations, not a renamed Settings link:
# a bottom bar whose fifth slot went straight to Settings left Analytics and
# Strategy Profile with no route on a phone except the collapsed rail.
#
# Order is deliberate. Analytics and Strategy Profile are work, the Partner is
# reflective work, and Settings is the quiet utility, so it sits last and keeps
# the muted treatment it has everywhere else in the product.
#
# The Partner is here and NOT in the rail: at rail widths it is a drawer, at
# bottom-nav widths it is this destination, and one conversation must not have
# two entry points at one width.
MOBILE_MORE = (
    ("/Analytics", "Analytics", "analytics"),
    ("/Strategy", "Strategy Profile", "flag"),
    ("/Partner", "AI Partner", "forum"),
    ("/Settings", "Settings", "settings"),
)

MOBILE_MORE_SLUGS = tuple(slug for slug, _label, _icon in MOBILE_MORE)


def _slug_from_url(url: str) -> str:
    """Reduce a full URL to the slug form used by the nav tables.

    Pure so the active-state logic is testable without a browser.
    """
    if not url:
        return ""
    path = urlparse(url).path.rstrip("/")
    if not path:
        return "/"
    return "/" + path.rsplit("/", 1)[-1]


def _active_slug(st) -> str:
    """Current destination, or "" when it cannot be determined.

    `st.context.url` is unavailable in registry-less AppTest boots, so this
    degrades to no active item rather than raising inside a render path.
    """
    try:
        return _slug_from_url(st.context.url or "")
    except Exception:  # noqa: BLE001 — render path must never raise
        return ""


def _nav_container_key(slug: str, active: bool) -> str:
    """Stable CSS hook for one nav row.

    Streamlit marks the current page only with a generated emotion class
    (`st-emotion-cache-<hash>`), which changes between releases and cannot
    be styled safely. Keying the container gives us `.st-key-…` instead, and
    the `_active` suffix carries the state — the same technique the trade
    calendar already uses for day outcomes.
    """
    name = "home" if slug == "/" else slug.strip("/").lower()
    return f"tl_nav_{name}_active" if active else f"tl_nav_{name}"


def route_href(slug: str, auth_token: object = None) -> str:
    """A hard-navigation URL that keeps the signed session recoverable.

    Streamlit's ``page_link`` performs soft navigation, but the custom mobile
    bar and HTML empty states use real anchors. A hard reload clears
    ``session_state``; the signed ``auth`` query token is what restores it.
    Query encoding is centralized here so reserved characters can never alter
    the destination or append an unintended parameter.
    """
    if auth_token is None or not str(auth_token):
        return slug
    return f"{slug}?{urlencode({'auth': str(auth_token)})}"


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


def _mobile_nav_html(active_slug: str, auth_token: object = None) -> str:
    """Fixed bottom navigation for narrow screens.

    Pure string builder. Uses the same Material Symbols family Streamlit
    already loads for the rail icons, so the product has one icon family
    rather than a second hand-rolled set. Every item pairs its icon with a
    text label; the current item is announced with aria-current, which
    Streamlit's own page_link does not emit.
    """
    items = []
    for slug, label, icon in MOBILE_NAV:
        is_active = slug == active_slug
        current = ' aria-current="page"' if is_active else ""
        state = " is-active" if is_active else ""
        href = escape(route_href(slug, auth_token), quote=True)
        items.append(
            f'<a class="tl-mobile-nav-item{state}" href="{href}"'
            f' target="_self"{current}>'
            f'<span class="tl-mobile-nav-icon" aria-hidden="true">{escape(icon)}</span>'
            f'<span class="tl-mobile-nav-label">{escape(label)}</span>'
            "</a>"
        )
    # More is a native <details>. A <summary> is focusable and toggles on
    # Enter or Space with no script at all, so the sheet is keyboard-
    # operable by construction rather than by an added handler — and it
    # still works if script never runs.
    #
    # It is NEVER rendered with `open`. A menu that reopens itself after
    # every navigation is a menu the trader has to dismiss on every page,
    # and on a phone it covers the content they just asked for. The bar
    # instead does what a tab bar does: the summary carries the current
    # state, so a trader on Analytics sees the More tab lit without the
    # sheet in the way — and finds Analytics marked when they open it.
    more_active = active_slug in MOBILE_MORE_SLUGS
    sheet = []
    for slug, label, icon in MOBILE_MORE:
        is_active = slug == active_slug
        # "true" rather than "page" on the nested link: the summary is the
        # navigation item representing the current location, and two
        # aria-current="page" in one nav announces the destination twice.
        current = ' aria-current="true"' if is_active else ""
        quiet = " is-quiet" if slug == "/Settings" else ""
        state = " is-active" if is_active else ""
        href = escape(route_href(slug, auth_token), quote=True)
        sheet.append(
            f'<a class="tl-mobile-more-item{quiet}{state}" href="{href}"'
            f' target="_self"{current}>'
            f'<span class="tl-mobile-more-icon" aria-hidden="true">'
            f"{escape(icon)}</span>"
            f"<span>{escape(label)}</span>"
            "</a>"
        )
    more_state = " is-active" if more_active else ""
    more_current = ' aria-current="page"' if more_active else ""
    items.append(
        '<details class="tl-mobile-more">'
        f'<summary class="tl-mobile-nav-item{more_state}"{more_current}>'
        '<span class="tl-mobile-nav-icon" aria-hidden="true">more_horiz</span>'
        '<span class="tl-mobile-nav-label">More</span>'
        "</summary>"
        '<div class="tl-mobile-more-sheet">'
        f'{"".join(sheet)}'
        "</div></details>"
    )
    return (
        '<nav class="tl-mobile-nav" aria-label="Primary">' f'{"".join(items)}' "</nav>"
    )


def _skip_link_html() -> str:
    """Keyboard escape from persistent navigation to the page workspace."""
    return (
        '<div class="tl-skip-shell">'
        '<a class="tl-skip-link" href="#tl-main-content">Skip to main content</a>'
        '<span id="tl-main-content" class="tl-main-anchor" tabindex="-1"></span>'
        "</div>"
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
    """Active-strategy context. Compact by design: it tells the trader which
    playbook their reviews are graded against, without competing with the
    destinations above it."""
    if strategy_name:
        return (
            '<div class="tl-side-note active">Active strategy: '
            f"<b>{escape(strategy_name)}</b></div>"
        )
    return (
        '<div class="tl-side-note">No active strategy. '
        "Add one in Strategy Profile.</div>"
    )


def render_primary_action(st) -> None:
    """The persistent "Log completed trade" action, directly under the brand.

    Rendered as a page_link inside a keyed container so it keeps soft
    navigation (and the registry-less fallback) while the design system can
    style it as the one filled action in the rail.
    """
    path, slug, label, icon = PRIMARY_ACTION
    with st.container(key="tl_nav_action"):
        _nav_link(st, path, slug, label, icon)


def render_mobile_navigation(st, active_path: str) -> None:
    """Five-item bottom navigation, shown only at the mobile breakpoint."""
    st.markdown(
        _mobile_nav_html(active_path, st.query_params.get("auth")),
        unsafe_allow_html=True,
    )


def render_sidebar(df=None, today=None) -> None:
    """Render the app shell: brand, primary action, destinations, active
    strategy context, and the quiet utility group.

    `df` / `today` are accepted for backward compatibility but unused — the
    sidebar no longer shows per-period stats, keeping navigation the focus.
    """
    import streamlit as st

    from src.tradelens.services.strategy import get_active_strategy
    from src.tradelens.ui.components.auth import (
        current_user,
        current_user_id,
        render_logout_button,
    )
    from src.tradelens.ui.design_system import get_asset_as_base64

    uid = current_user_id()
    strategy = get_active_strategy(uid) if uid is not None else None
    strategy_name = (strategy or {}).get("name")
    active = _active_slug(st)

    # First focusable control in the workspace. The target sits immediately
    # before page content, so keyboard users can bypass the persistent rail.
    st.markdown(_skip_link_html(), unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(
            _brand_html(get_asset_as_base64("logo_mark.png")), unsafe_allow_html=True
        )

        render_primary_action(st)

        for path, slug, label, icon in PRIMARY_NAV:
            is_active = slug == active
            with st.container(key=_nav_container_key(slug, is_active)):
                _nav_link(st, path, slug, label, icon)
                if is_active:
                    # page_link emits no aria-current, so the only way to
                    # announce the current destination is to say it.
                    st.markdown(
                        '<span class="tl-visually-hidden">Current page</span>',
                        unsafe_allow_html=True,
                    )

        st.markdown(_strategy_badge_html(strategy_name), unsafe_allow_html=True)

        st.divider()
        for path, slug, label, icon in UTILITY_NAV:
            with st.container(key=_nav_container_key(slug, slug == active)):
                _nav_link(st, path, slug, label, icon)

        uname = current_user()
        if uname:
            st.caption(f"Signed in as: **{uname}**")
        render_logout_button()

    # Outside the rail: the bar is fixed to the viewport and must stay
    # reachable when the rail is collapsed off-canvas on a phone.
    render_mobile_navigation(st, active)

    # The AI Partner rides the shell for the same reason the bar does — it is
    # global, and every page already calls this one function. Both render
    # nothing when closed, and the launcher is `display: none` below the
    # sidebar-navigation width, which takes it out of the tab order rather
    # than merely hiding it; the phone gets the full destination instead.
    # Always offered, on every destination including the Partner route. Which
    # of the two presentations a width actually gets is decided by two
    # complementary media queries — the launcher and drawer are hidden below
    # 768, the full page is hidden from 768 up — so exactly one exists at any
    # width without this function needing to know which route is rendering.
    from src.tradelens.ui.components.partner_panel import (
        render_partner_drawer,
        render_partner_launcher,
    )

    render_partner_launcher(st)
    render_partner_drawer(st)

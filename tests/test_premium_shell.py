"""
Tests for the premium app shell and navigation architecture (Task 2).

The shell is the one piece of UI present on every destination, so its
contract is structural rather than cosmetic:

- exactly FIVE primary destinations, in the approved reading order;
- "Log completed trade" is a persistent ACTION, not a sixth destination;
- Settings sits in a quiet utility group, outside the primary set;
- renaming is presentational only — page files and URL slugs never move,
  because a slug is a bookmark someone already has;
- mobile navigation is a separate hierarchy (max five items), not the
  desktop rail shrunk down;
- every interactive state carries a non-colour cue.
"""

import re
from pathlib import Path

from src.tradelens.ui.components import sidebar

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Primary navigation
# ---------------------------------------------------------------------------


def test_primary_nav_has_exactly_five_destinations():
    """Five is the ceiling the spec sets, and the ceiling bottom navigation
    can carry on mobile. A sixth destination means something was promoted
    that should have been grouped."""
    assert len(sidebar.PRIMARY_NAV) == 5


def test_primary_nav_matches_the_target_information_architecture():
    assert sidebar.PRIMARY_NAV == (
        ("app.py", "/", "Overview", ":material/space_dashboard:"),
        ("pages/2_Trades.py", "/Trades", "Journal", ":material/menu_book:"),
        ("pages/4_Analytics.py", "/Analytics", "Analytics", ":material/analytics:"),
        ("pages/6_Insights.py", "/Insights", "AI Reviews", ":material/psychology:"),
        ("pages/5_Strategy.py", "/Strategy", "Strategy Profile", ":material/flag:"),
    )


def test_relabelling_never_moves_a_page_file_or_a_url():
    """Dashboard became Overview and Insights & Review became AI Reviews.
    Both are presentation: a moved slug breaks every existing bookmark and
    every link the marketing site or a password-reset email may hold."""
    slugs = {slug for _, slug, _, _ in sidebar.PRIMARY_NAV}
    paths = {path for path, _, _, _ in sidebar.PRIMARY_NAV}
    assert slugs == {"/", "/Trades", "/Analytics", "/Insights", "/Strategy"}
    assert paths == {
        "app.py",
        "pages/2_Trades.py",
        "pages/4_Analytics.py",
        "pages/6_Insights.py",
        "pages/5_Strategy.py",
    }
    for path, _, _, _ in sidebar.PRIMARY_NAV:
        assert (ROOT / "src" / "tradelens" / "ui" / path).is_file(), path


def test_old_labels_are_gone_from_the_primary_group():
    labels = {label for _, _, label, _ in sidebar.PRIMARY_NAV}
    assert "Dashboard" not in labels
    assert "Insights & Review" not in labels
    assert {"Overview", "AI Reviews"} <= labels


def test_every_destination_pairs_an_icon_with_a_text_label():
    """Icon-only navigation harms discoverability; the label is the control."""
    for _path, _slug, label, icon in sidebar.PRIMARY_NAV:
        assert label and not label.startswith(":material/")
        assert icon.startswith(":material/") and icon.endswith(":")


# ---------------------------------------------------------------------------
# The persistent action
# ---------------------------------------------------------------------------


def test_logging_a_trade_is_an_action_not_a_sixth_destination():
    """New Trade is the one thing a trader comes here to do, so it is a
    button above the list rather than a peer of the places they browse."""
    paths = {path for path, _, _, _ in sidebar.PRIMARY_NAV}
    assert "pages/1_NewTrade.py" not in paths

    assert sidebar.PRIMARY_ACTION == (
        "pages/1_NewTrade.py",
        "/NewTrade",
        "Log completed trade",
        ":material/add_chart:",
    )


def test_primary_action_copy_is_post_trade_and_unambiguous():
    _, _, label, _ = sidebar.PRIMARY_ACTION
    assert label == "Log completed trade"
    lowered = label.lower()
    for banned in ("signal", "live trade", "buy now", "go long", "go short", "alert"):
        assert banned not in lowered


# ---------------------------------------------------------------------------
# Utility group
# ---------------------------------------------------------------------------


def test_settings_is_present_but_outside_the_primary_group():
    primary_slugs = {slug for _, slug, _, _ in sidebar.PRIMARY_NAV}
    assert "/Settings" not in primary_slugs

    utility_slugs = {slug for _, slug, _, _ in sidebar.UTILITY_NAV}
    assert "/Settings" in utility_slugs


def test_every_pre_redesign_destination_is_still_reachable():
    """Regrouping must not strand a route. Every page the old flat menu
    exposed still has a home somewhere in the shell."""
    reachable = (
        {slug for _, slug, _, _ in sidebar.PRIMARY_NAV}
        | {slug for _, slug, _, _ in sidebar.UTILITY_NAV}
        | {sidebar.PRIMARY_ACTION[1]}
    )
    for slug in (
        "/",
        "/NewTrade",
        "/Trades",
        "/Analytics",
        "/Insights",
        "/Strategy",
        "/Settings",
    ):
        assert slug in reachable, f"{slug} became unreachable"


# ---------------------------------------------------------------------------
# Mobile navigation — a separate hierarchy, not a shrunken rail
# ---------------------------------------------------------------------------


def test_mobile_navigation_carries_at_most_five_items():
    """Four journey tabs plus More is the five-item ceiling."""
    assert 0 < len(sidebar.MOBILE_NAV) + 1 <= 5


def test_mobile_navigation_leads_with_the_required_mobile_journeys():
    """Spec 13: the required mobile journeys are Overview, Log, Journal and
    AI Review. Those four lead; the fifth slot is More."""
    slugs = [slug for slug, _, _ in sidebar.MOBILE_NAV]
    assert slugs[:4] == ["/", "/NewTrade", "/Trades", "/Insights"]


def test_mobile_labels_are_short_enough_for_a_bottom_bar():
    for _slug, label, _icon in sidebar.MOBILE_NAV:
        assert len(label) <= 8, f"{label!r} will wrap in a 5-up bottom bar"


def test_mobile_navigation_does_not_duplicate_the_desktop_hierarchy():
    """Spec 10: mobile navigation is its own hierarchy. If it were the same
    five destinations it would just be the rail, shrunk."""
    desktop = [slug for _, slug, _, _ in sidebar.PRIMARY_NAV]
    mobile = [slug for slug, _, _ in sidebar.MOBILE_NAV]
    assert mobile != desktop


# ---------------------------------------------------------------------------
# Render surface
# ---------------------------------------------------------------------------


def test_shell_renderers_exist_and_are_callable():
    for name in (
        "render_sidebar",
        "render_primary_action",
        "render_mobile_navigation",
    ):
        assert callable(getattr(sidebar, name)), name


def test_nav_link_keeps_its_registry_less_fallback():
    """page_link needs the multipage registry, which standalone AppTest
    boots do not build. Losing the fallback turns every page test into a
    crash instead of a boot."""
    source = Path(sidebar.__file__).read_text(encoding="utf-8")
    assert "st.page_link(" in source
    assert "except Exception" in source


def test_mobile_navigation_markup_is_escaped_and_labelled():
    html = sidebar._mobile_nav_html("/")
    assert 'class="tl-mobile-nav"' in html
    # four journey tabs plus the More summary, which is the fifth tab
    assert html.count("tl-mobile-nav-item") == len(sidebar.MOBILE_NAV) + 1
    # a nav landmark, so screen readers can skip to and past it
    assert "<nav" in html and 'aria-label="Primary"' in html
    for _slug, label, _icon in sidebar.MOBILE_NAV:
        assert f">{label}<" in html
    assert ">More<" in html


def test_mobile_navigation_marks_the_current_destination():
    """Current location must be announced, not just tinted."""
    html = sidebar._mobile_nav_html("/Trades")
    assert 'aria-current="page"' in html
    assert html.count('aria-current="page"') == 1
    assert "is-active" in html


def test_mobile_navigation_preserves_the_signed_auth_token():
    """A bottom-nav click performs a hard navigation. Dropping the signed
    query token there signs the trader out even though their session is valid."""
    html = sidebar._mobile_nav_html(
        "/Trades", auth_token="signed token?with&reserved=characters"
    )
    assert 'href="/NewTrade?auth=signed+token%3Fwith%26reserved%3Dcharacters"' in html
    # every tab AND every destination inside More — a sheet link that drops
    # the token signs the trader out just as surely as a tab that does.
    assert html.count("?auth=") == len(sidebar.MOBILE_NAV) + len(sidebar.MOBILE_MORE)
    for slug, _label, _icon in sidebar.MOBILE_MORE:
        assert f'href="{slug}?auth=' in html


def test_route_href_is_plain_without_a_token_and_encoded_with_one():
    assert sidebar.route_href("/NewTrade") == "/NewTrade"
    assert sidebar.route_href("/Settings", "") == "/Settings"
    assert sidebar.route_href("/Trades", "a&b=c") == "/Trades?auth=a%26b%3Dc"


def test_live_empty_state_fallbacks_preserve_the_signed_session():
    """Registry-less page boots use real anchors, so they need the same
    signed-session recovery URL as the mobile shell."""
    pages_dir = ROOT / "src" / "tradelens" / "ui" / "pages"
    for filename in ("4_Analytics.py", "6_Insights.py"):
        source = (pages_dir / filename).read_text(encoding="utf-8")
        assert "route_href" in source
        assert 'st.query_params.get("auth")' in source
        assert '<a href="/NewTrade"' not in source


def test_mobile_navigation_tolerates_an_unknown_path():
    html = sidebar._mobile_nav_html("/SomewhereElse")
    assert 'aria-current="page"' not in html
    assert 'class="tl-mobile-nav"' in html


# ---------------------------------------------------------------------------
# Active-destination detection
# ---------------------------------------------------------------------------


def test_slug_is_derived_from_the_browser_url():
    cases = {
        "http://localhost:8501/": "/",
        "http://localhost:8501": "/",
        "http://localhost:8501/Trades": "/Trades",
        "http://localhost:8501/Trades/": "/Trades",
        "https://app.tradelensai.io/Analytics?auth=abc": "/Analytics",
        "": "",
    }
    for url, expected in cases.items():
        assert sidebar._slug_from_url(url) == expected, url


def test_active_slug_degrades_instead_of_raising():
    """st.context is unavailable in registry-less boots. No active item is a
    fine outcome; an exception in the shell blanks every page."""

    class _NoContext:
        @property
        def context(self):
            raise RuntimeError("no script run context")

    assert sidebar._active_slug(_NoContext()) == ""


def test_nav_container_key_carries_the_active_state():
    assert sidebar._nav_container_key("/", False) == "tl_nav_home"
    assert sidebar._nav_container_key("/", True) == "tl_nav_home_active"
    assert sidebar._nav_container_key("/Trades", True) == "tl_nav_trades_active"
    # keys become CSS class names, so they must stay selector-safe
    for _path, slug, _label, _icon in sidebar.PRIMARY_NAV + sidebar.UTILITY_NAV:
        for state in (True, False):
            key = sidebar._nav_container_key(slug, state)
            assert key.replace("_", "").isalnum(), key


def test_active_state_does_not_depend_on_streamlits_emotion_hash():
    """Streamlit marks the current page with a generated class whose hash
    changes between releases. Styling it would break on the next upgrade."""
    from src.tradelens.ui import design_system as ds

    assert "st-emotion-cache" not in ds.build_css()


# ---------------------------------------------------------------------------
# Shell CSS contract
# ---------------------------------------------------------------------------


def _css() -> str:
    from src.tradelens.ui import design_system as ds

    return ds.build_css()


def test_nav_rows_meet_the_touch_target_minimum():
    """Measured in the browser before the shell pass: 32px."""
    css = _css()
    block = css[css.index('[data-testid="stPageLink-NavLink"] {') :][:420]
    assert "min-height: 44px" in block


def test_active_destination_has_a_non_colour_cue():
    """Colour alone cannot carry 'you are here'."""
    css = _css()
    marker = '[class*="st-key-tl_nav_"][class*="_active"]'
    assert marker in css
    block = css[css.index(marker) :][:700]
    assert "font-weight" in block, "weight change is the type-level cue"
    assert (
        "::before" in css[css.index(marker) :][:1200]
    ), "indicator bar is the shape cue"


def test_nav_states_are_all_defined():
    css = _css()
    for state in (":hover", ":focus-visible", ":active"):
        assert f'[data-testid="stPageLink-NavLink"]{state}' in css, state


def test_nav_hover_is_gated_to_hover_capable_pointers():
    """A latched hover on touch reads as a selected destination."""
    css = _css()
    hover_rule = css.index('[data-testid="stPageLink-NavLink"]:hover')
    preceding = css[:hover_rule]
    assert (
        preceding.rindex("(hover: hover) and (pointer: fine)")
        > preceding.rindex("@media") - 1
    )


def test_mobile_bar_is_hidden_on_desktop_and_shown_on_phones():
    css = _css()
    assert ".tl-mobile-nav {" in css
    desktop = css[css.index(".tl-mobile-nav {") :][:260]
    assert "display: none" in desktop, "the bar must not exist on desktop"
    assert "@media (max-width: 767px)" in css


def test_mobile_bar_reserves_its_own_space():
    """A fixed bar that covers the last row of a table is a bug, not a bar."""
    css = _css()
    mobile_block = css[css.index("@media (max-width: 767px)") :]
    assert "padding-bottom" in mobile_block
    assert "safe-area-inset-bottom" in mobile_block, "phones have a gesture bar"


def test_mobile_bar_items_meet_the_touch_target_minimum():
    css = _css()
    block = css[css.index(".tl-mobile-nav-item {") :][:420]
    assert "min-height: 44px" in block


def test_mobile_bar_outranks_streamlits_markdown_anchor_rule():
    """Verified in the browser: an unanchored `.tl-mobile-nav-item` selector
    loses to Streamlit's own markdown-anchor rule, and the whole bar renders
    in default link blue with underlines."""
    css = _css()
    assert '[data-testid="stAppViewContainer"] a.tl-mobile-nav-item' in css
    assert '[data-testid="stAppViewContainer"] a.tl-mobile-nav-item.is-active' in css
    block = css[css.index('[data-testid="stAppViewContainer"] a.tl-mobile-nav-item') :][
        :520
    ]
    assert "text-decoration: none" in block
    assert "color: var(--tl-text-muted)" in block


def test_the_rail_holds_exactly_one_filled_action():
    """Spec 8: one primary action per screen. Sign out rendered as a second
    filled teal button, which gave the rail two things shouting equally."""
    css = _css()
    action = css[css.index(".st-key-tl_nav_action [data-testid=") :][:300]
    assert "background: var(--tl-focus)" in action

    signout = css[css.index('[data-testid="stSidebar"] .stButton > button {') :][:300]
    assert "background: transparent" in signout
    assert "var(--tl-focus)" not in signout, "sign out must not be a second primary"


def test_shell_motion_is_restrained_and_reduced_motion_safe():
    """Emil: transform/opacity only, under 300ms, and never on a keyboard
    navigation. Nav rows are visited dozens of times a session, so they get
    colour feedback and a press response — nothing that has to finish."""
    css = _css()
    shell = css[css.index("/* === APP SHELL") :]
    assert "transition: all" not in shell
    for duration in ("0.4s", "400ms", "500ms"):
        assert duration not in shell
    reduced = css[css.index("prefers-reduced-motion") :]
    assert "tl-mobile-nav-item" in reduced or "transition: none" in reduced


def test_shell_has_a_keyboard_skip_path_to_page_content():
    html = sidebar._skip_link_html()
    assert 'href="#tl-main-content"' in html
    assert 'id="tl-main-content"' in html
    assert 'tabindex="-1"' in html
    assert "Skip to main content" in html

    css = _css()
    assert "a.tl-skip-link" in css
    focus = css[css.index("a.tl-skip-link:focus-visible") :][:220]
    assert "transform: none" in focus


# ---------------------------------------------------------------------------
# More — the fifth mobile slot (Task 11 correction)
# ---------------------------------------------------------------------------


def test_the_fifth_mobile_slot_is_more_not_a_renamed_settings_link():
    """Spec 10: the bottom bar is Home, Log, Journal, Review, More — and
    Analytics, Strategy Profile and Settings live under More. A fifth slot
    wired straight to Settings leaves the other two with no route on a
    phone except the collapsed rail."""
    assert len(sidebar.MOBILE_NAV) == 4
    assert [slug for slug, _, _ in sidebar.MOBILE_NAV] == [
        "/",
        "/NewTrade",
        "/Trades",
        "/Insights",
    ]
    assert [slug for slug, _, _ in sidebar.MOBILE_MORE] == [
        "/Analytics",
        "/Strategy",
        "/Settings",
    ]
    html = sidebar._mobile_nav_html("/")
    assert ">More<" in html
    # Settings is reachable, but not as the tab itself
    assert 'class="tl-mobile-nav-item" href="/Settings"' not in html


def test_more_is_operable_without_script():
    """A native <details>: the summary is focusable and toggles on Enter or
    Space with no handler, so the sheet works for a keyboard user and
    survives script never running."""
    html = sidebar._mobile_nav_html("/")
    assert "<details" in html and "<summary" in html
    assert "onclick" not in html and "<script" not in html
    # closed by default when the trader is elsewhere
    detail = html[html.index("<details") : html.index("<summary")]
    assert "open" not in detail


def test_more_is_never_rendered_open():
    """A menu that reopens itself after every navigation is one the trader
    has to dismiss on every page, and on a phone it covers the content they
    just asked for. The bar does what a tab bar does instead."""
    for slug in ("/", "/Trades", "/Analytics", "/Strategy", "/Settings"):
        html = sidebar._mobile_nav_html(slug)
        detail = html[html.index("<details") : html.index("<summary")]
        assert " open" not in detail, f"{slug} rendered More already open"


def test_the_more_tab_carries_the_current_state_for_its_destinations():
    """On Analytics the More tab is lit and announced, without the sheet in
    the way — and the nested destination is still identified when the sheet
    is opened by hand."""
    for slug, label in (
        ("/Analytics", "Analytics"),
        ("/Strategy", "Strategy Profile"),
        ("/Settings", "Settings"),
    ):
        html = sidebar._mobile_nav_html(slug)
        summary = html[html.index("<summary") : html.index("</summary>")]
        assert "is-active" in summary, f"{slug}: More tab is not lit"
        assert 'aria-current="page"' in summary, f"{slug}: More tab not announced"
        # exactly one "page" in the whole bar — the summary's
        assert html.count('aria-current="page"') == 1
        # …and the nested link keeps its own identification, on a distinct
        # token so the destination is not announced twice
        assert f'href="{slug}" target="_self" aria-current="true"' in html
        assert f">{label}<" in html


def test_a_destination_outside_more_leaves_the_more_tab_quiet():
    html = sidebar._mobile_nav_html("/Trades")
    summary = html[html.index("<summary") : html.index("</summary>")]
    assert "is-active" not in summary
    assert "aria-current" not in summary
    assert 'aria-current="true"' not in html


def test_settings_stays_visually_secondary_inside_more():
    """It is present and reachable, never a third piece of work."""
    html = sidebar._mobile_nav_html("/")
    assert 'class="tl-mobile-more-item is-quiet" href="/Settings"' in html
    for slug in ("/Analytics", "/Strategy"):
        assert f'class="tl-mobile-more-item" href="{slug}"' in html

    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    quiet = css[css.index(".tl-mobile-more-item.is-quiet") :]
    quiet = quiet[: quiet.index("}")]
    assert "var(--tl-text-muted)" in quiet
    assert "border-top" in quiet, "the utility is separated, not just dimmed"


def test_the_more_sheet_meets_the_touch_floor():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    block = css[css.index(".tl-mobile-more-item,") :]
    block = block[: block.index("}")]
    assert "min-height: 44px" in block


def test_the_more_reveal_is_withdrawn_under_reduced_motion():
    """Emil: opening a panel over a fixed bar is a state change worth
    conveying, but only for readers who have not asked for less motion."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    start = css.index("@media (prefers-reduced-motion: no-preference)")
    depth, i = 0, css.index("{", start)
    while i < len(css):
        depth += (css[i] == "{") - (css[i] == "}")
        if depth == 0:
            break
        i += 1
    opt_in = css[start : i + 1]
    assert "tl-more-in" in opt_in
    assert "animation: tl-more-in" not in css[:start]
    frames = re.search(r"@keyframes tl-more-in \{(.*?)\n  \}", css, re.S)
    assert frames, "no keyframes for the More reveal"
    for banned in ("width", "height", "margin", "padding"):
        assert banned not in frames.group(1), banned


def test_a_closed_more_sheet_is_gone_for_the_keyboard_too():
    """A closed <details> collapses its content out of the layout — but an
    absolutely positioned child escapes that. The sheet was invisible and
    still tabbable, so a keyboard user landed on three links inside a shut
    menu. Caught by measuring tabbability in the browser, not by looking."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    rule = re.search(
        r"\.tl-mobile-more:not\(\[open\]\) > \.tl-mobile-more-sheet \{([^{}]*)\}",
        css,
    )
    assert rule, "nothing hides the sheet while More is closed"
    assert "display: none" in rule.group(1)

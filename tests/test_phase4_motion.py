"""Phase 4 — motion and interaction refinement.

Guards for the four motions this phase added, plus the two file-wide rules it
is meant to keep true. Each one is written to fail for a specific reason; the
handoff records the mutation that was used to check it.
"""

import re
from pathlib import Path

from src.tradelens.ui import design_system as ds

_PAGES = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"


def _css() -> str:
    return ds.build_css()


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _enclosing_media(css: str, needle: str) -> str:
    """The text of the `@media` prelude that most closely encloses ``needle``.

    Used to prove a guard sits on the declaration itself rather than relying on
    a kill switch elsewhere in the file, which source order can silently
    defeat when two rules share specificity.
    """
    at = css.index(needle)
    opened = css.rfind("@media", 0, at)
    assert opened != -1, f"{needle!r} is not inside any media query"
    return css[opened : css.index("{", opened)]


def _keyframes(css: str, name: str) -> str:
    match = re.search(r"@keyframes " + re.escape(name) + r"\s*\{(.*?)\n  \}", css, re.S)
    assert match, f"no keyframes named {name}"
    return match.group(1)


# ── The Partner drawer ────────────────────────────────────────────────────
# The drawer curve and duration tokens were defined in Phase 2 and applied
# nowhere; the drawer simply appeared. These pin the fix.


def test_the_drawer_entrance_uses_the_drawer_curve_and_duration():
    """The one motion in the product that is a drawer should be the one that
    uses the drawer curve. Both tokens existed unused before Phase 4."""
    # The selector appears twice: the base layout rule, and the entrance rule
    # inside the opt-in block. Join every body so the test names the property
    # it wants rather than the position of the rule that carries it.
    css = _strip_comments(_css())
    bodies = re.findall(r"\.st-key-tl_partner_drawer \{([^{}]*)\}", css)
    assert bodies, "the drawer has no rules at all"
    body = "\n".join(bodies)
    assert "animation: tl-drawer-in" in body
    assert "var(--tl-dur-drawer)" in body, "duration is not the drawer token"
    assert "var(--tl-ease-drawer)" in body, "easing is not the drawer curve"


def test_the_drawer_entrance_is_withdrawn_under_reduced_motion():
    """A 420px panel sliding in is exactly the movement reduced motion asks
    us to drop. It must be guarded where it is declared."""
    css = _strip_comments(_css())
    prelude = _enclosing_media(css, "animation: tl-drawer-in")
    assert "prefers-reduced-motion: no-preference" in prelude


def test_the_drawer_grows_from_the_launcher_corner():
    """Spatial consistency: the drawer is opened by a button pinned to the
    bottom-right, so it must enter from the bottom-right rather than from the
    middle of a 420px panel."""
    css = _strip_comments(_css())
    bodies = "\n".join(re.findall(r"\.st-key-tl_partner_drawer \{([^{}]*)\}", css))
    assert "transform-origin: 100% 100%" in bodies


def test_the_drawer_entrance_animates_nothing_that_costs_layout():
    frames = _keyframes(_strip_comments(_css()), "tl-drawer-in")
    for banned in ("width", "height", "margin", "padding", "top", "left"):
        assert banned not in frames, f"drawer entrance animates {banned}"


# ── Press feedback ────────────────────────────────────────────────────────


def test_press_feedback_never_reaches_a_keyboard_activation():
    """`:active` DOES match while Space is held on a focused button, so a bare
    `:active` scale would animate a keyboard activation — which the phase
    forbids outright. `:not(:focus-visible)` is what separates the two, and it
    is the whole reason the rule is split from the colour change."""
    css = _strip_comments(_css())
    rule = re.search(r"([^{}]*)\{\s*transform: scale\(0\.97\);\s*\}", css)
    assert rule, "no press-scale rule found"
    selector = rule.group(1)
    assert ":not(:focus-visible)" in selector
    # every selector in the group must carry the guard, not just the first
    for part in selector.split(","):
        if part.strip():
            assert ":not(:focus-visible)" in part, f"unguarded selector: {part.strip()}"


def test_the_colour_half_of_press_feedback_survives_the_keyboard():
    """Reduced motion and keyboard operation lose the movement, not the
    acknowledgement. A control must still say it was heard."""
    css = _strip_comments(_css())
    rule = re.search(
        r"\.stButton button:active,\s*\.stFormSubmitButton button:active \{([^{}]*)\}",
        css,
    )
    assert rule, "buttons lost their :active colour change"
    assert "background:" in rule.group(1)
    assert "transform" not in rule.group(1)


def test_press_feedback_is_withdrawn_under_reduced_motion():
    css = _strip_comments(_css())
    reduce_at = css.index("@media (prefers-reduced-motion: reduce)")
    depth, i = 0, css.index("{", reduce_at)
    while i < len(css):
        depth += (css[i] == "{") - (css[i] == "}")
        if depth == 0:
            break
        i += 1
    block = css[reduce_at : i + 1]
    assert ".stButton button:active:not(:focus-visible)" in block
    assert ".stFormSubmitButton button:active:not(:focus-visible)" in block


# ── The dock-inspired rail ────────────────────────────────────────────────


def test_the_rail_icon_scale_is_guarded_where_it_is_declared():
    """The regression this test exists for was real and was introduced by this
    phase. The rail icon rule sits ~150 lines AFTER the global reduced-motion
    kill switch with identical specificity (0,5,0), so a `transform: none`
    listed in that switch loses on source order and the icon keeps scaling.
    The guard therefore has to be on the declaration's own media query.

    Mutation: move the guard back to the kill switch and this fails.
    """
    css = _strip_comments(_css())
    prelude = _enclosing_media(css, "transform: scale(1.06)")
    assert "prefers-reduced-motion: no-preference" in prelude, (
        "the rail icon scale relies on a distant kill switch that source "
        "order defeats"
    )


def test_the_rail_icon_scale_is_gated_to_fine_pointers():
    """On touch, `:hover` latches after a tap and would leave one icon
    permanently enlarged — a second active state beside the real one."""
    prelude = _enclosing_media(_strip_comments(_css()), "transform: scale(1.06)")
    assert "hover: hover" in prelude
    assert "pointer: fine" in prelude


def test_the_rail_icon_scale_stays_inside_the_approved_band():
    """1.05-1.08 was the approved ceiling. Anything more moves an icon far
    enough to read as the dock magnification that was explicitly rejected."""
    css = _strip_comments(_css())
    scales = [
        float(v)
        for v in re.findall(
            r'\[data-testid="stIconMaterial"\] \{\s*transform: scale\(([\d.]+)\)', css
        )
    ]
    assert scales, "no rail icon scale found"
    for value in scales:
        assert 1.05 <= value <= 1.08, f"rail icon scale {value} is outside 1.05-1.08"


def test_the_rail_never_animates_a_width():
    """The rejected half of the dock. Animating width would displace the
    neighbouring destination while a trader is aiming at it."""
    css = _strip_comments(_css())
    prelude_at = css.index("transform: scale(1.06)")
    opened = css.rfind("@media", 0, prelude_at)
    depth, i = 0, css.index("{", opened)
    while i < len(css):
        depth += (css[i] == "{") - (css[i] == "}")
        if depth == 0:
            break
        i += 1
    block = css[opened : i + 1]
    for banned in ("width", "margin", "padding", "gap"):
        assert banned not in block, f"the rail hover animates {banned}"


# ── The Analytics lens ────────────────────────────────────────────────────


def test_the_analytics_lens_panel_is_keyed_by_the_lens():
    """The key is what makes the reveal honest. Keyed by the lens, it mounts
    only on a lens change; keyed by a counter it would replay on every rerun,
    which on Streamlit means on every widget interaction on the page."""
    source = (_PAGES / "4_Analytics.py").read_text()
    assert 'st.container(key=f"tl_lens_{lens.lower()}")' in source


def test_the_lens_reveal_is_withdrawn_under_reduced_motion():
    prelude = _enclosing_media(
        _strip_comments(_css()), "animation: tl-lens-in-performance"
    )
    assert "prefers-reduced-motion: no-preference" in prelude


def test_the_lens_reveal_animates_nothing_that_costs_layout():
    css = _strip_comments(_css())
    for name in ("performance", "risk", "timing", "setups"):
        frames = _keyframes(css, f"tl-lens-in-{name}")
        for banned in ("width", "height", "margin", "padding", "top", "left"):
            assert banned not in frames, f"lens reveal {name} animates {banned}"


def test_each_lens_has_its_own_animation_name():
    """The fix for a defect the browser found, and the guard that keeps it.

    A single rule on `[class*="st-key-tl_lens_"]` matched every lens, so when
    Streamlit reused the container node and swapped only its class,
    `animation-name` never changed and the entrance never retriggered.
    Measured with real `animationstart` events: it fired on an unrelated rerun
    that remounted the page, and did NOT fire on the lens change itself.

    One name per lens is what makes a lens change a change of animation-name.
    A shared substring selector reintroduces the defect, so it must not
    return.
    """
    css = _strip_comments(_css())
    assert (
        '[class*="st-key-tl_lens_"]' not in css
    ), "a shared lens selector cannot retrigger on a lens change"
    for name in ("performance", "risk", "timing", "setups"):
        assert f".st-key-tl_lens_{name} {{" in css
        assert f"animation: tl-lens-in-{name}" in css
        assert f"@keyframes tl-lens-in-{name}" in css


def test_the_lens_keyframes_do_not_drift_apart():
    """They are generated from one template; this pins that they stay
    identical, so a lens cannot quietly acquire a different entrance."""
    css = _strip_comments(_css())
    bodies = {
        name: " ".join(_keyframes(css, f"tl-lens-in-{name}").split())
        for name in ("performance", "risk", "timing", "setups")
    }
    assert len(set(bodies.values())) == 1, bodies


# ── File-wide rules ───────────────────────────────────────────────────────


def test_no_rule_transitions_all():
    """`transition: all` animates properties nobody chose, including ones that
    cost layout."""
    assert "transition: all" not in _strip_comments(_css())


def test_nothing_enters_from_zero_scale():
    """Nothing in the real world appears from nothing. Every scale entrance in
    this product starts at 0.9 or above."""
    css = _strip_comments(_css())
    for value in re.findall(r"scale\(([\d.]+)\)", css):
        assert float(value) >= 0.9, f"scale({value}) is below the 0.9 floor"


def test_no_ui_motion_uses_ease_in():
    """ease-in delays the first movement, at the exact moment the user is
    watching most closely, so it reads as lag."""
    css = _strip_comments(_css())
    # `ease-in-out` is legitimate; a bare `ease-in` is not.
    assert not re.search(r"ease-in(?![-a-z])", css), "a bare ease-in is present"


# The single permitted duration above the ceiling, named rather than implied.
# It is a constant loop reporting ongoing work, not a transition between two
# states, so the "UI motion stays under 300ms" rule does not describe it.
_LONG_DURATION_EXEMPTIONS = {"tl-skeleton-pulse": 1400}

# Every declaration that can carry a duration. `--tl-dur-*` is included
# because the transition rules reference the tokens rather than literals, so a
# scan of `transition:` alone would read `var(--tl-dur-state)` and see no
# number at all.
_DURATION_DECL = re.compile(
    r"(--tl-dur-[a-z-]+|transition-duration|animation-duration|transition|animation)"
    r"\s*:\s*([^;{}]+)[;}]",
    re.I,
)
_TIME_TOKEN = re.compile(r"(?<![\w.-])(\d*\.?\d+)(ms|s)(?![\w-])", re.I)


def _durations_ms(value: str):
    """Every time literal in a declaration value, normalised to milliseconds.

    Handles integer and decimal seconds as well as milliseconds, and returns
    one entry per value in a multi-value declaration such as
    ``transition-duration: 160ms, 120ms``.
    """
    out = []
    for number, unit in _TIME_TOKEN.findall(value):
        ms = float(number) * (1000.0 if unit.lower() == "s" else 1.0)
        out.append(ms)
    return out


def test_every_duration_stays_under_the_300ms_ceiling():
    """The ceiling, enforced in whatever unit it is written in.

    The previous form matched `(\\d+)ms` only. A second-denominated duration —
    `0.4s`, `1s`, `.5s` — was invisible to it, so the rule could be broken by
    changing units. It also never looked at `--tl-dur-*`, which is where the
    numbers actually live, since the transition rules reference tokens.
    """
    css = _strip_comments(_css())
    offenders = []
    for prop, value in _DURATION_DECL.findall(css):
        exempt = any(name in value for name in _LONG_DURATION_EXEMPTIONS)
        for ms in _durations_ms(value):
            if ms > 300 and not exempt:
                offenders.append(f"{prop}: {value.strip()} -> {ms:g}ms")
    assert not offenders, "durations above the 300ms UI ceiling:\n" + "\n".join(
        offenders
    )


def test_the_only_long_duration_is_the_named_skeleton_pulse():
    """The exemption is narrow by construction: it is keyed to an animation
    NAME, so it cannot be borrowed by an unrelated rule that merely happens to
    also want 1.4s."""
    css = _strip_comments(_css())
    long_ones = []
    for _prop, value in _DURATION_DECL.findall(css):
        for ms in _durations_ms(value):
            if ms > 300:
                long_ones.append((value.strip(), ms))
    for value, ms in long_ones:
        name = next((n for n in _LONG_DURATION_EXEMPTIONS if n in value), None)
        assert name, f"un-exempted long duration: {value} ({ms:g}ms)"
        assert ms == _LONG_DURATION_EXEMPTIONS[name], (
            f"{name} is exempt at {_LONG_DURATION_EXEMPTIONS[name]}ms, "
            f"found {ms:g}ms — the exemption is a value, not a licence"
        )


def test_the_duration_guard_reads_seconds_as_well_as_milliseconds():
    """A guard for the guard. If the parser stops understanding seconds, the
    ceiling silently stops being enforced, and nothing else would notice."""
    assert _durations_ms("0.4s") == [400.0]
    assert _durations_ms("1s") == [1000.0]
    assert _durations_ms(".5s") == [500.0]
    assert _durations_ms("160ms") == [160.0]
    assert _durations_ms("160ms, 120ms") == [160.0, 120.0]
    assert _durations_ms("opacity 0.2s ease, transform 120ms ease") == [200.0, 120.0]
    # An easing curve's bare numbers are not durations.
    assert _durations_ms("cubic-bezier(0.23, 1, 0.32, 1)") == []

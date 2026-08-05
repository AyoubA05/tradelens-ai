"""Contract tests for the one dark token system.

Two live colour systems (D1) and a planned name retarget that would have
silently flipped six existing names (D2) are what these tests exist to
prevent. A deleted name must stay deleted: an alias is how D1 happened.
"""

import re
from pathlib import Path

import pytest

from src.tradelens.ui import design_system as ds
from tests.test_design_system import contrast_ratio

SURFACES = (
    "TL_SURFACE_CANVAS",
    "TL_SURFACE_RAIL",
    "TL_SURFACE_PANEL",
    "TL_SURFACE_ELEVATED",
    "TL_SURFACE_CHART",
    "TL_SURFACE_FIELD",
)

# Deleted in this task, never aliased. Spec §2 and §4.1.
DELETED_TOKENS = (
    "TL_CANVAS",
    "TL_PAPER",
    "TL_MIST",
    "TL_INK",
    "TL_MUTED",
    "TL_HAIRLINE",
    "TL_ACTION",
    "TL_ACTION_HOVER",
    "TL_SUCCESS_INK",
    "TL_DANGER_INK",
    "TL_WARNING_INK",
    "TL_SUCCESS_WASH",
    "TL_DANGER_WASH",
    "TL_WARNING_WASH",
    "TL_ACTION_WASH",
    "TL_RAIL",
    "TL_CHART_STAGE",
    "TL_BG",
    "TL_SURFACE",
    "TL_SURFACE_2",
    "TL_BORDER",
    "TL_BORDER_SUBTLE",
    "TL_TEXT",
    "TL_TEXT_MUTED",
    "TL_TEXT_FAINT",
)

Z_SCALE = (
    ("TL_Z_BASE", 0),
    ("TL_Z_RAISED", 10),
    ("TL_Z_PARTNER", 20),
    ("TL_Z_NAV", 30),
    ("TL_Z_SHEET", 40),
    ("TL_Z_OVERLAY", 50),
)


def test_every_role_token_exists_and_is_a_hex_colour():
    names = SURFACES + (
        "TL_CONTENT_PRIMARY",
        "TL_CONTENT_SECONDARY",
        "TL_LINE_HAIRLINE",
        "TL_LINE_STRONG",
        "TL_ACCENT_ACTION",
    )
    for name in names:
        value = getattr(ds, name)
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), f"{name} = {value!r}"


def test_body_text_clears_aa_on_every_surface():
    for surface in SURFACES:
        bg = getattr(ds, surface)
        for fg_name in ("TL_CONTENT_PRIMARY", "TL_CONTENT_SECONDARY"):
            ratio = contrast_ratio(getattr(ds, fg_name), bg)
            assert ratio >= 4.5, f"{fg_name} on {surface} = {ratio:.2f}"


def test_semantic_colours_clear_aa_on_every_surface():
    for surface in SURFACES:
        bg = getattr(ds, surface)
        for fg_name in ("TL_PRIMARY", "TL_SUCCESS", "TL_DANGER", "TL_WARNING"):
            ratio = contrast_ratio(getattr(ds, fg_name), bg)
            assert ratio >= 4.5, f"{fg_name} on {surface} = {ratio:.2f}"


def test_grade_ramp_clears_aa_on_the_panel_surface():
    # Grade chips move from the deleted light PAPER onto the dark panel, so
    # the whole ramp is re-pointed at the dark semantic family.
    for name in ("TL_GRADE_A", "TL_GRADE_B", "TL_GRADE_C", "TL_GRADE_D", "TL_GRADE_F"):
        ratio = contrast_ratio(getattr(ds, name), ds.TL_SURFACE_PANEL)
        assert ratio >= 4.5, f"{name} on panel = {ratio:.2f}"


def test_line_strong_is_a_usable_boundary_on_every_surface():
    # D4: rail vs canvas separates at 1.02:1, so tone cannot carry a boundary.
    # All six, not just three: the drawer edge sits on ELEVATED, which is the
    # lightest surface and therefore the binding constraint.
    for surface in SURFACES:
        ratio = contrast_ratio(ds.TL_LINE_STRONG, getattr(ds, surface))
        assert ratio >= 3.0, f"TL_LINE_STRONG on {surface} = {ratio:.2f}"


def test_the_hairline_stays_quieter_than_the_strong_line():
    """Two line weights that measure the same are one line weight."""
    assert contrast_ratio(ds.TL_LINE_HAIRLINE, ds.TL_SURFACE_CANVAS) < contrast_ratio(
        ds.TL_LINE_STRONG, ds.TL_SURFACE_CANVAS
    )


@pytest.mark.parametrize("name", DELETED_TOKENS)
def test_superseded_tokens_are_deleted_not_aliased(name):
    assert not hasattr(ds, name), (
        f"{name} still exists. Superseded names are deleted so a stale import "
        f"fails loudly instead of silently changing meaning (D1/D2)."
    )


def test_z_scale_is_defined_and_ordered():
    values = [getattr(ds, name) for name, _ in Z_SCALE]
    assert values == [expected for _, expected in Z_SCALE]
    assert values == sorted(values)


def test_navigation_always_outranks_the_partner():
    # A trader must never dismiss a chat surface to reach navigation (§4.5).
    assert ds.TL_Z_PARTNER < ds.TL_Z_NAV < ds.TL_Z_SHEET < ds.TL_Z_OVERLAY


def test_css_declares_no_z_index_outside_the_scale():
    """Every stylesheet the product injects, not just the main one.

    auth_screen.py builds its own <style> block and was the one place still
    carrying a bare `z-index: 1` for the sign-in card. A scale that only one
    file is measured against is a convention, not a contract.
    """
    from src.tradelens.ui.components.auth_screen import auth_css

    allowed = {str(v) for _n, v in Z_SCALE}
    for name, css in (("build_css", ds.build_css()), ("auth_css", auth_css())):
        for raw in re.findall(r"z-index:\s*([^;]+);", css):
            value = raw.strip()
            assert (
                value.startswith("var(--tl-z-") or value in allowed
            ), f"{name}: raw z-index {value!r} outside the scale — see §4.5"


def test_the_auth_card_still_sits_above_its_background_and_scrim():
    """Tokenising the layering must not reorder it."""
    from src.tradelens.ui.components import auth_screen

    css = auth_screen.auth_css()
    bg = _z_for(css, ".tl-auth-bg")
    scrim = _z_for(css, ".tl-auth-scrim")
    card = _z_for(css, ".tl-auth-card")
    assert bg == scrim == ds.TL_Z_BASE
    assert card == ds.TL_Z_RAISED
    assert card > scrim >= bg


def _z_for(css: str, selector: str) -> int:
    """The z-index declared in the block that names `selector`."""
    block = css.split(selector, 1)[1].split("}", 1)[0]
    match = re.search(r"z-index:\s*(\d+)\s*;", block)
    assert match, f"no z-index in the {selector} block"
    return int(match.group(1))


def test_css_exposes_every_role_as_a_custom_property():
    css = ds.build_css()
    for prop in (
        "--tl-surface-canvas",
        "--tl-surface-rail",
        "--tl-surface-panel",
        "--tl-surface-elevated",
        "--tl-surface-chart",
        "--tl-surface-field",
        "--tl-content-primary",
        "--tl-content-secondary",
        "--tl-line-hairline",
        "--tl-line-strong",
        "--tl-accent-action",
        "--tl-z-base",
        "--tl-z-raised",
        "--tl-z-partner",
        "--tl-z-nav",
        "--tl-z-sheet",
        "--tl-z-overlay",
    ):
        assert f"{prop}:" in css, f"{prop} missing from :root"


def test_no_page_module_declares_a_colour_literal():
    ui = Path("src/tradelens/ui")
    offenders = []
    for path in list(ui.glob("pages/*.py")) + [ui / "app.py"]:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"#[0-9A-Fa-f]{6}\b", line):
                offenders.append(f"{path}:{lineno}")
    assert not offenders, f"colour literals outside design_system: {offenders}"


def test_no_css_variable_is_used_without_being_defined():
    """A var() with no definition silently inherits.

    This caught a real one: the skip link set `color: var(--tl-rail-ink)`,
    which was never defined anywhere, so the link inherited its colour onto a
    near-black background. A token system whose references can dangle is not a
    contract.
    """
    css = ds.build_css()
    defined = set(re.findall(r"(--tl-[a-z0-9-]+)\s*:", css))
    used = set(re.findall(r"var\((--tl-[a-z0-9-]+)", css))
    dangling = sorted(used - defined)
    assert not dangling, f"var() references with no definition: {dangling}"


def test_rail_and_canvas_are_separated_by_a_line_not_by_tone():
    """D4: rail vs canvas is 1.02:1. Tone alone cannot carry the boundary,
    so the rail must draw an explicit strong edge."""
    css = ds.build_css()
    rail_rules = [
        block
        for block in css.split("}")
        if "stSidebar" in block and "border-right" in block
    ]
    assert rail_rules, "the rail declares no right edge"
    assert any("--tl-line-strong" in block for block in rail_rules)


def test_shell_surfaces_use_role_variables_not_literals():
    css = ds.build_css()
    body = css.split(":root", 1)[1].split("}", 1)[1]
    literals = re.findall(r"(?<!-)#[0-9A-Fa-f]{6}\b", body)
    assert not literals, f"raw colours outside :root: {sorted(set(literals))[:10]}"


def test_the_compatibility_bridge_is_gone():
    """Task 1 aliased the old CSS variable names to the new roles so the
    product kept rendering between the two tasks. Task 2 retargets the rules,
    so the aliases must go — a bridge nobody crosses is just a second name for
    everything, which is the state Task 1 existed to end."""
    css = ds.build_css()
    retired = (
        "--tl-canvas",
        "--tl-paper",
        "--tl-mist",
        "--tl-ink",
        "--tl-muted",
        "--tl-hairline",
        "--tl-action",
        "--tl-action-hover",
        "--tl-success-ink",
        "--tl-danger-ink",
        "--tl-warning-ink",
        "--tl-success-wash",
        "--tl-danger-wash",
        "--tl-warning-wash",
        "--tl-action-wash",
        "--tl-rail",
        "--tl-chart-stage",
        "--tl-bg",
        "--tl-surface",
        "--tl-surface-2",
        "--tl-border",
        "--tl-border-subtle",
        "--tl-text",
        "--tl-text-muted",
        "--tl-text-faint",
    )
    found = sorted(
        name for name in retired if re.search(re.escape(name) + r"(?![-a-z0-9])", css)
    )
    assert not found, f"compatibility bridge still present: {found}"


def test_no_empty_state_icon_is_an_emoji():
    """D9, scoped honestly: the empty-state renderers only.

    This covers exactly three call sites' worth of surface —
    ``render_empty_state``, ``render_data_state``, and Analytics' local
    ``_empty`` adapter — because those are the Phase 1 D9 finding. It does
    NOT cover the rest of the product: toast icons, button labels, subheaders
    and the corrections sidebar still carry emoji, and they belong to the
    tasks that own those surfaces (8, 9, 12, 13). A guard that claimed more
    than it checked would be worse than no guard.

    Within that scope the rule is: icons are Material ligature names — plain
    escaped text styled by the font the mobile nav relies on. Emoji are
    font-dependent, carry their own colour, and cannot be token-controlled.

    Typographic VALUES are not icons and are deliberately excluded — the
    infinity sign for an undefined profit factor, delta arrows, the stepper
    tick, ledger result marks, and em-dash placeholders all carry meaning as
    text.
    """
    ui = Path("src/tradelens/ui")
    renderers = ("render_empty_state", "render_data_state", "_empty")
    pattern = re.compile(r"\b(" + "|".join(renderers) + r")\(", re.M)
    offenders = []
    for path in sorted(ui.rglob("*.py")):
        if "_archive" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            window = source[match.end() : match.end() + 400]
            depth, end = 1, 0
            for i, ch in enumerate(window):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            args = window[:end]
            for literal in re.findall(r'"([^"\n]*)"', args):
                if not literal:
                    continue
                if re.fullmatch(r"[a-z0-9_]+", literal):
                    continue  # a ligature name
                if len(literal) <= 2 and not literal.isascii():
                    line = source[: match.start()].count("\n") + 1
                    offenders.append(f"{path.name}:{line} {literal!r}")
    assert not offenders, (
        "empty-state icons must be Material ligature names, not emoji "
        f"(this guard covers {', '.join(renderers)} only): {offenders}"
    )


def test_the_empty_state_icon_uses_the_material_font():
    css = ds.build_css()
    block = [b for b in css.split("}") if ".tl-empty-card .icon" in b]
    assert block, "no rule styles the empty-state icon"
    assert "Material Symbols Rounded" in block[0]


def test_an_absent_icon_emits_no_element():
    """An empty icon used to render a 32px box with a margin and nothing in
    it — a hole in the layout where a mark was supposed to be."""
    assert '<div class="icon">' not in ds.render_empty_state("", "T", "B")
    assert '<div class="icon">' in ds.render_empty_state("insights", "T", "B")


def test_no_ui_module_references_a_retired_css_variable():
    """The bridge deletion had to reach page-level CSS too.

    design_system.py is not the only file that emits `var(--tl-*)`: pages
    build inline styles for money colours and captions. Retargeting only the
    stylesheet left nine references pointing at variables that no longer
    exist, which resolve to nothing and silently inherit.
    """
    retired = (
        "--tl-canvas",
        "--tl-paper",
        "--tl-mist",
        "--tl-ink",
        "--tl-muted",
        "--tl-hairline",
        "--tl-action",
        "--tl-action-hover",
        "--tl-action-wash",
        "--tl-success-ink",
        "--tl-danger-ink",
        "--tl-warning-ink",
        "--tl-success-wash",
        "--tl-danger-wash",
        "--tl-warning-wash",
        "--tl-rail",
        "--tl-chart-stage",
        "--tl-bg",
        "--tl-surface",
        "--tl-surface-2",
        "--tl-border",
        "--tl-border-subtle",
        "--tl-text",
        "--tl-text-muted",
        "--tl-text-faint",
    )
    pattern = re.compile(
        "(" + "|".join(sorted(retired, key=len, reverse=True)) + r")(?![-a-z0-9])"
    )
    offenders = []
    for path in sorted(Path("src/tradelens/ui").rglob("*.py")):
        if "_archive" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            line = source[: match.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line} {match.group(1)}")
    assert not offenders, f"retired CSS variables still referenced: {offenders}"

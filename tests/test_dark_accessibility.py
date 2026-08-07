"""Cross-page accessibility and containment checks for the dark workspace.

Containment is asserted against **rendered output** — the elements AppTest
actually emits — not against a subprocess's stdout. Stdout proves a page exited
zero; it does not prove what a trader would have read on the screen, and a leaked
DSN is precisely a thing that renders without failing.

The pages themselves are not booted in-process here. In a pytest process the
database engine is already bound from import time, so booting a real page would
read whatever DATABASE_URL pointed at when the suite started — a developer's own
journal. Instead the two halves are separated:

  * the containment *renderer* is driven with real leaky exceptions through the
    real error_box builder, and its emitted elements are inspected;
  * every page's own except-blocks are checked structurally, so a page that
    starts rendering an exception object is caught without booting it.

The remaining page-level checks — heading order, tab order, target sizes — are
browser work and live in this task's browser step.
"""

import ast
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.tradelens.ui import design_system as ds
from src.tradelens.ui.components.ui import error_box
from tests.test_design_system import contrast_ratio

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "src" / "tradelens" / "ui"
PAGES_DIR = UI_DIR / "pages"

# Strings that must never reach a rendered element, whatever went wrong.
SECRETS = (
    "Traceback",
    "postgresql://",
    "sqlite:///",
    "sk-ant-",
    "psycopg",
    "ANTHROPIC_API_KEY",
    "OperationalError",
    "SMTP_PASSWORD",
)

# A representative leaky exception per failure class the product actually has.
LEAKY_EXCEPTIONS = {
    "database": (
        "OperationalError",
        'psycopg2.OperationalError: could not connect: dsn="postgresql://tl:hunter2@db:5432/tradelens"',
    ),
    "ai": (
        "AuthenticationError",
        "anthropic.AuthenticationError: invalid x-api-key sk-ant-api03-AAAABBBB",
    ),
    "mail": (
        "SMTPAuthenticationError",
        "smtplib.SMTPAuthenticationError: (535) SMTP_PASSWORD rejected for tl@example.com",
    ),
}


def rendered_text(at) -> str:
    """Every string this app run actually put on the screen."""
    parts = []
    for element in at.main:
        value = getattr(element, "value", None)
        if isinstance(value, str):
            parts.append(value)
    for element in at.sidebar:
        value = getattr(element, "value", None)
        if isinstance(value, str):
            parts.append(value)
    for exc in at.exception:
        parts.append(str(getattr(exc, "value", exc)))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Containment, asserted on what renders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", sorted(LEAKY_EXCEPTIONS))
def test_an_unexpected_failure_renders_fixed_copy_and_leaks_nothing(kind):
    """The real containment shape: log the exception, render fixed copy.

    Driven through the real error_box builder so the assertion covers the
    string a trader would actually see.
    """
    exc_name, message = LEAKY_EXCEPTIONS[kind]
    script = f"""
import logging
import streamlit as st
from src.tradelens.ui.components.ui import error_box

log = logging.getLogger("tradelens.test")
try:
    raise RuntimeError({message!r})
except Exception:
    log.exception("{exc_name} during a {kind} operation")
    st.markdown(
        error_box("Something went wrong. Please try again."),
        unsafe_allow_html=True,
    )
"""
    at = AppTest.from_string(script, default_timeout=30)
    at.run()

    assert not at.exception, "the failure escaped containment and rendered"
    screen = rendered_text(at)
    assert "Something went wrong" in screen
    for secret in SECRETS:
        assert secret not in screen, f"{kind}: rendered output leaked {secret!r}"


def test_the_containment_probe_can_actually_detect_a_leak():
    """A negative test that never fails proves nothing. Render the exception
    the way a careless handler would, and confirm the probe catches it."""
    script = """
import streamlit as st
try:
    raise RuntimeError('psycopg2 dsn="postgresql://tl:hunter2@db:5432/tradelens"')
except Exception as exc:
    st.markdown(f"Could not load: {exc}")
"""
    at = AppTest.from_string(script, default_timeout=30)
    at.run()
    screen = rendered_text(at)
    assert any(secret in screen for secret in SECRETS)


def test_the_error_builder_escapes_what_it_is_handed():
    """The containment copy is fixed, but the builder must still escape: a
    domain error's own message can carry characters that would otherwise close
    the surrounding tag."""
    html = error_box("<script>alert(1)</script> & more")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_a_raised_exception_surfaces_as_an_apptest_exception():
    """Pins the other half of the probe: an uncontained failure is visible."""
    at = AppTest.from_string("raise RuntimeError('boom')", default_timeout=30)
    at.run()
    assert at.exception


# ---------------------------------------------------------------------------
# Every page's own handlers, checked without booting them
# ---------------------------------------------------------------------------
def _page_sources():
    """Live pages only. pages/_archive holds superseded files that are not
    imported by anything, and auditing them reports defects nobody can reach."""
    for path in sorted(PAGES_DIR.glob("*.py")):
        yield path
    yield UI_DIR / "app.py"


def _live_ui_sources():
    for path in sorted(UI_DIR.rglob("*.py")):
        if "_archive" in path.parts:
            continue
        yield path


def _is_broad(handler) -> bool:
    """Whether this handler catches everything rather than a named domain type."""
    node = handler.type
    if node is None:
        return True
    names = node.elts if isinstance(node, ast.Tuple) else [node]
    return any(
        isinstance(n, ast.Name) and n.id in {"Exception", "BaseException"}
        for n in names
    )


@pytest.mark.parametrize("path", list(_page_sources()), ids=lambda p: p.name)
def test_no_handler_renders_the_exception_it_caught(path):
    """`except Exception as e: st.error(e)` is the shape that leaks a DSN.

    Only *broad* handlers are flagged. A domain exception is designed to be
    read by a trader — 2_Trades.py deliberately renders OutcomeMismatch next to
    the two fields that disagree — so rendering one is correct, not a leak.
    The rule is about catching everything and showing whatever came back.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    renders = {
        "markdown",
        "write",
        "error",
        "warning",
        "info",
        "caption",
        "text",
        "toast",
    }
    offenders = []

    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        if not handler.name or not _is_broad(handler):
            continue
        for call in (n for n in ast.walk(handler) if isinstance(n, ast.Call)):
            func = call.func
            if not (isinstance(func, ast.Attribute) and func.attr in renders):
                continue
            for node in ast.walk(call):
                if isinstance(node, ast.Name) and node.id == handler.name:
                    offenders.append(
                        f"{path.name}:{call.lineno} renders {handler.name}"
                    )

    assert not offenders, offenders


# ---------------------------------------------------------------------------
# Composited contrast
# ---------------------------------------------------------------------------
RGBA_OVER = {
    "TL_PRIMARY_DIM": "TL_SURFACE_PANEL",
    "TL_SUCCESS_DIM": "TL_SURFACE_PANEL",
    "TL_DANGER_DIM": "TL_SURFACE_PANEL",
    "TL_WARNING_DIM": "TL_SURFACE_PANEL",
    "TL_NEUTRAL_DIM": "TL_SURFACE_PANEL",
}


def composite(rgba: str, backdrop_hex: str) -> str:
    """Flatten an rgba() layer onto an opaque backdrop, returning #RRGGBB.

    Treating the first rgba() layer as opaque is how contrast bugs survive
    tests: the ratio that matters is the one against the composite.
    """
    match = re.fullmatch(
        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", rgba.strip()
    )
    assert match, f"not an rgba() literal: {rgba!r}"
    fr, fg, fb = (int(match.group(i)) for i in (1, 2, 3))
    alpha = float(match.group(4))
    back = backdrop_hex.lstrip("#")
    br, bg, bb = (int(back[i : i + 2], 16) for i in (0, 2, 4))
    out = [
        round(f * alpha + b * (1 - alpha)) for f, b in ((fr, br), (fg, bg), (fb, bb))
    ]
    return "#%02X%02X%02X" % tuple(out)


def test_composite_flattens_a_known_layer_correctly():
    assert composite("rgba(255,255,255,1.0)", "#000000") == "#FFFFFF"
    assert composite("rgba(255,255,255,0.0)", "#101B20") == "#101B20"
    assert composite("rgba(255,255,255,0.5)", "#000000") == "#808080"


needs_task_one = pytest.mark.skipif(
    not hasattr(ds, "TL_SURFACE_PANEL"),
    reason="Task 1 introduces the role tokens; this activates once it lands",
)


@needs_task_one
@pytest.mark.parametrize("token", sorted(RGBA_OVER))
def test_primary_text_clears_aa_on_every_composited_tint(token):
    flat = composite(getattr(ds, token), getattr(ds, RGBA_OVER[token]))
    ratio = contrast_ratio(ds.TL_CONTENT_PRIMARY, flat)
    assert ratio >= 4.5, f"{token} composites to {flat} = {ratio:.2f}"


# ---------------------------------------------------------------------------
# Tenant scoping at the call site
# ---------------------------------------------------------------------------
SCOPED_CALLS = {
    "get_trades",
    "get_trade",
    "create_trade",
    "update_trade",
    "delete_trade",
    "get_active_strategy",
    "upsert_strategy_profile",
    "count_sample_trades",
    "get_weekly_review",
    "build_global_partner_context",
}

# Call sites that pass the owner inside a payload dict rather than as a keyword.
# Each is listed explicitly with the line that carries the owner, so the
# exemption is auditable instead of a silent hole in the regex.
PAYLOAD_SCOPED = {
    # 1_NewTrade.py builds `data` with "user_id": uid before handing it to
    # _persist(); create_trade(data) is scoped through that dict.
    ("1_NewTrade.py", "create_trade"),
}


def test_every_scoped_service_call_site_names_an_owner():
    """Tenant scoping resolved at the call site, not only inside the service.

    AST-based: a regex window mistook `create_trade(data)` for an unscoped call
    because the owner is set twenty lines earlier, and swept pages/_archive,
    which nothing imports.
    """
    offenders = []
    for path in _live_ui_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            func = call.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None
            )
            if name not in SCOPED_CALLS:
                continue
            if (path.name, name) in PAYLOAD_SCOPED:
                continue
            scoped = any(kw.arg in {"user_id", "uid"} for kw in call.keywords)
            scoped = scoped or any(
                isinstance(a, ast.Name) and a.id in {"user_id", "uid"}
                for a in call.args
            )
            if not scoped:
                offenders.append(f"{path.name}:{call.lineno} {name}")
    assert not offenders, f"unscoped service calls: {offenders}"


def test_the_payload_scoped_allowlist_has_no_dead_entries():
    """An exemption for a call site that no longer exists hides a real one."""
    for filename, call_name in PAYLOAD_SCOPED:
        matches = [p for p in _live_ui_sources() if p.name == filename]
        assert matches, f"allowlisted file is gone: {filename}"
        assert f"{call_name}(" in matches[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Heading sequence — the two skips the browser sweep reproduced
# ---------------------------------------------------------------------------
#
# The sweep is the instrument for heading order, because Streamlit composes
# final levels at render time. These two guards pin the specific defects it
# found so they cannot come back through a source edit:
#
#   Overview  h2 -> h4  (`overview_bands.render_ranked_list`)
#   Strategy  h1 -> h5  (the playbook form's first section heading)


def test_the_ranked_list_heading_sits_directly_under_its_band():
    """It renders inside a band whose own heading is an h2, so an h4 skips a
    level and announces a section that is not there."""
    source = (UI_DIR / "components" / "overview_bands.py").read_text(encoding="utf-8")
    assert '<h3 class="tl-ranked-title">' in source
    assert "<h4" not in source


def test_the_playbook_form_heading_does_not_skip_three_levels():
    """`#####` renders an h5 immediately under the page's h1."""
    source = (PAGES_DIR / "5_Strategy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    levels = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "markdown"
            and node.args
        ):
            continue
        arg = node.args[0]
        # The heading marker is in the literal head of the string, whether it
        # is a plain constant or an f-string.
        head = None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            head = arg.value
        elif isinstance(arg, ast.JoinedStr) and arg.values:
            first = arg.values[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                head = first.value
        if head:
            match = re.match(r"^(#{1,6})\s", head)
            if match:
                levels.append(len(match.group(1)))
    # Read from the markdown calls, not the raw text: an explanatory comment
    # about the wrong marker contains the wrong marker, which is the third
    # contract in this phase a comment has broken.
    assert levels, "no markdown headings found on the playbook page"
    # The page title is an h1 rendered by the masthead, so the first markdown
    # heading must be an h2 and the sequence must not skip. A first attempt
    # asserted `max(levels) <= 3`, which the browser then showed still skipped
    # h2 — the number was easier to satisfy than the property.
    sequence = [1] + levels
    skips = [f"{a}->{b}" for a, b in zip(sequence, sequence[1:]) if b - a > 1]
    assert not skips, f"heading levels {sequence} skip {skips}"


def test_no_live_ui_source_emits_a_heading_below_h4():
    """h5 and h6 have no styles in this design system, so one appearing is
    always an accident rather than a choice."""
    offenders = []
    for path in _live_ui_sources():
        text = path.read_text(encoding="utf-8")
        for marker in ("<h5", "<h6"):
            if marker in text:
                offenders.append(f"{path.name}: {marker}")
    assert not offenders, offenders

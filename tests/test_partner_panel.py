"""The Partner surface owns presentation and nothing else.

Handoff §1 approves the global Partner only through the existing service.
These tests are the boundary: a new endpoint, a direct SDK import, an
unscoped query, or a double usage log is a scope violation, not a bug.
"""

import ast
from pathlib import Path

import pytest

from src.tradelens.ui.components import partner_panel, partner_turn

_PATH = Path(__file__).resolve().parents[1] / (
    "src/tradelens/ui/components/partner_panel.py"
)
_SOURCE = _PATH.read_text(encoding="utf-8")
_TREE = ast.parse(_SOURCE)


class _FakeSt:
    """Enough Streamlit to render the surface and read what it produced.

    Only the calls this module actually makes. Anything else raising is the
    point: a surface that starts using a widget this does not model should
    fail loudly here rather than be silently untested.
    """

    def __init__(self, state=None):
        self.session_state = dict(state or {})
        self.html = []
        self.text = []
        self.buttons = []

    # rendering
    def markdown(self, body, unsafe_allow_html=False):
        (self.html if unsafe_allow_html else self.text).append(str(body))

    def button(self, label, **kwargs):
        self.buttons.append(label)
        return False

    def chat_input(self, label, **kwargs):
        self.text.append(str(label))
        return None

    # containers
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def container(self, *a, **k):
        return self._Ctx()

    def chat_message(self, *a, **k):
        return self._Ctx()

    def spinner(self, *a, **k):
        return self._Ctx()

    def rerun(self):
        raise AssertionError("rerun during a render-only assertion")


def _calls(name: str):
    """Every call to `name`, found through the AST.

    Not a substring count. `"log_ai_usage("` also matches a definition, a
    wrapper, a docstring and a comment — the plan's version of the
    once-per-response test counted all of those and would have reported two
    for a module with a single call site.
    """
    out = []
    for node in ast.walk(_TREE):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        ident = getattr(func, "id", None) or getattr(func, "attr", None)
        if ident == name:
            out.append(node)
    return out


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "banned", ["import anthropic", "from anthropic", "Anthropic(", "requests.post"]
)
def test_the_surface_never_reaches_the_model_directly(banned):
    assert banned not in _SOURCE


def test_the_surface_opens_no_data_access_path_of_its_own():
    for banned in ("get_session", "SessionLocal", "session.query", "select("):
        assert banned not in _SOURCE, f"{banned}: context comes from the adapter only"


def test_context_is_built_by_the_approved_adapter_only():
    assert "build_global_partner_context" in _SOURCE
    # …and it is handed to the send path rather than called with a literal.
    assert "build_context=build_global_partner_context" in _SOURCE


def test_the_authenticated_user_id_is_what_reaches_the_send_path():
    body = ast.dump(
        next(
            n
            for n in ast.walk(_TREE)
            if isinstance(n, ast.FunctionDef) and n.name == "render_partner_body"
        )
    )
    assert "current_user_id" in body
    assert "user_id" in body


def test_partner_reply_is_called_in_general_reflective_mode():
    """The panel wires the service; `per_trade_qa=False` is the send path's
    call, so the property is asserted where the call is made."""
    turn_src = (
        Path(__file__).resolve().parents[1]
        / "src/tradelens/ui/components/partner_turn.py"
    ).read_text(encoding="utf-8")
    assert "per_trade_qa=False" in turn_src
    assert "partner_reply=partner_reply" in _SOURCE


def test_usage_is_logged_from_exactly_one_place():
    """One wiring, one call site. A second would bill a trader twice for one
    answer."""
    assert _SOURCE.count("log_ai_usage=log_ai_usage") == 1
    assert _calls("log_ai_usage") == [], "the panel must not invoke the logger itself"
    turn_src = (
        Path(__file__).resolve().parents[1]
        / "src/tradelens/ui/components/partner_turn.py"
    ).read_text(encoding="utf-8")
    assert turn_src.count('log_ai_usage("AI Partner"') == 1


def test_model_output_never_takes_an_html_allowing_path():
    """Authored chrome may use unsafe_allow_html; a stored turn's content may
    not. Asserted through the AST — a text window reports on whatever happens
    to sit nearby."""
    unsafe = []
    for node in ast.walk(_TREE):
        if not isinstance(node, ast.Call):
            continue
        if not any(
            k.arg == "unsafe_allow_html"
            and isinstance(k.value, ast.Constant)
            and k.value.value is True
            for k in node.keywords
        ):
            continue
        dumped = ast.dump(
            ast.Module(body=[ast.Expr(a) for a in node.args], type_ignores=[])
        )
        for generated in ("content", "reply"):
            if f"'{generated}'" in dumped or f'"{generated}"' in dumped:
                unsafe.append((node.lineno, generated))
    assert not unsafe, f"model output on an HTML-allowing path: {unsafe}"


def test_every_value_the_surface_paints_into_markup_is_escaped():
    """Labels come from the trader's own records, which are their text.

    Asserted by rendering rather than by reading the source: the label list is
    built in two steps, so an AST rule strict enough to catch a real hole also
    flags the safe intermediate. What matters is the markup that comes out.
    """
    hostile = '<img src=x onerror=alert(1)> & "quoted"'
    fake = _FakeSt()
    partner_panel._render_turn(
        fake,
        {
            "role": "assistant",
            "content": "an answer",
            partner_turn.CONTEXT_FIELD: [hostile],
        },
    )
    html = "\n".join(fake.html)
    assert hostile not in html
    assert "<img" not in html
    assert "&lt;img" in html


# ---------------------------------------------------------------------------
# Scope: this product reviews trades that already closed
# ---------------------------------------------------------------------------


def test_every_suggested_question_is_retrospective():
    forward = (
        "should i",
        "will ",
        "predict",
        "forecast",
        "entry",
        "target",
        "buy",
        "sell",
        "next trade",
        "setup today",
    )
    for chip in partner_panel.SUGGESTED_QUESTIONS:
        lowered = chip.lower()
        for token in forward:
            assert token not in lowered, f"forward-looking chip: {chip!r}"


def test_the_surface_never_implies_advice():
    lowered = (partner_panel.EMPTY_STATE_BODY + " " + partner_panel.SCOPE_NOTE).lower()
    for banned in ("recommend", "advice", "signal", "you should", "prediction"):
        if banned in lowered:
            # Only acceptable inside an explicit denial.
            assert "never" in lowered or "not " in lowered, banned


def test_the_scope_sentence_is_stated_once_not_per_turn():
    """Repeating it under every answer is how a disclaimer stops being read."""
    render = next(
        n
        for n in ast.walk(_TREE)
        if isinstance(n, ast.FunctionDef) and n.name == "_render_turn"
    )
    assert "SCOPE_NOTE" not in ast.dump(render)


def test_the_empty_state_says_the_conversation_is_not_saved():
    assert "not saved" in partner_panel.EMPTY_STATE_BODY.lower()


def test_the_empty_state_names_the_three_context_sources():
    body = partner_panel.EMPTY_STATE_BODY.lower()
    for source in ("journal", "completed trades", "strategy profile"):
        assert source in body, source


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_history_is_scoped_per_user():
    assert partner_turn.history_key(7) != partner_turn.history_key(8)


def test_the_drawer_does_not_claim_modal_semantics_it_cannot_enforce():
    """No focus trap exists without script, so claiming aria-modal would be
    worse than not claiming it (spec §8.2).

    Read off the rendered markup. A source scan flagged the docstring that
    explains why the attribute is absent — the third time in this phase a
    contract has been broken by a comment about the thing it guards.
    """
    fake = _FakeSt(state={partner_panel.PARTNER_OPEN_KEY: True})
    partner_panel.render_partner_drawer(fake)
    html = "\n".join(fake.html)
    assert "aria-modal" not in html
    assert 'aria-label="AI Partner"' in html


def test_the_close_control_is_first_in_the_drawer_dom_order():
    """There is no Esc-to-close without script, so the visible control is the
    only way out and a keyboard user must reach it before the conversation."""
    drawer = _SOURCE[_SOURCE.index("def render_partner_drawer") :]
    assert drawer.index('"Close"') < drawer.index("render_partner_body")


def test_a_closed_drawer_renders_nothing_at_all():
    """Not CSS-hidden: a hidden-but-present drawer keeps its widgets in the
    tab order, and there is no script here to manage that."""
    for name in ("render_partner_drawer", "render_partner_launcher"):
        fn = next(
            n
            for n in ast.walk(_TREE)
            if isinstance(n, ast.FunctionDef) and n.name == name
        )
        # Each guards on PARTNER_OPEN_KEY and returns before rendering.
        assert isinstance(fn.body[1], ast.If), name
        assert any(isinstance(n, ast.Return) for n in ast.walk(fn.body[1])), name


def test_the_launcher_is_a_real_widget_not_authored_html():
    """Authored HTML cannot be tabbed to or activated without script."""
    launcher = _SOURCE[_SOURCE.index("def render_partner_launcher") :]
    launcher = launcher[: launcher.index("def render_partner_drawer")]
    assert "st.button(" in launcher
    assert "<button" not in launcher


def test_the_phone_has_no_floating_launcher_and_it_is_not_merely_hidden():
    """`display: none` takes it out of the tab order. `visibility: hidden` or
    an offscreen transform would leave a keyboard user able to reach a control
    they cannot see."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    phone = css[css.rindex("@media (max-width: 767px)") :]
    block_start = phone.index(".st-key-tl_partner_launcher")
    block = phone[block_start : phone.index("}", block_start) + 1]
    assert "display: none" in block
    assert ".st-key-tl_partner_drawer" in block


def test_the_drawer_sits_on_the_partner_layer():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    block = css[css.index(".st-key-tl_partner_drawer {") :][:400]
    assert "var(--tl-z-partner)" in block
    assert "position: fixed" in block


def test_the_partner_rides_the_shell_every_page_already_renders():
    """One wiring, so a new page cannot forget it and an old one cannot get a
    second copy."""
    sidebar = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/components/sidebar.py"
    ).read_text(encoding="utf-8")
    assert sidebar.count("render_partner_launcher(st)") == 1
    assert sidebar.count("render_partner_drawer(st)") == 1
    pages = (Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages").glob(
        "*.py"
    )
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "render_partner_launcher" not in text, page.name

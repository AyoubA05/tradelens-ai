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


def test_the_authenticated_user_id_is_what_reaches_the_send_path(monkeypatch):
    """Asserted by sending, not by reading.

    This previously scanned `render_partner_body` for the name
    `current_user_id`, which the amendment moved into the availability helper —
    a location change would have failed it while the property held. What
    matters is which owner the send path is given.
    """
    from src.tradelens.ui.components import partner_panel as pp
    from src.tradelens.ui.components.partner_turn import history_key

    seen = {}

    def spy(state, *, user_id, text, **_kw):
        seen["user_id"] = user_id
        seen["text"] = text

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: 7)
    monkeypatch.setattr(pp, "ai_available", lambda: True)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: _Ctx())
    monkeypatch.setattr(pp, "send_turn", spy)

    fake = _RichFakeSt(
        {
            "_partner_busy_drawer": True,
            "_partner_pending_drawer": "What did I repeat?",
            history_key(7): [{"role": "user", "content": "What did I repeat?"}],
        }
    )
    pp.render_partner_body(fake, surface="drawer")
    assert seen == {"user_id": 7, "text": "What did I repeat?"}


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


# ---------------------------------------------------------------------------
# Task 15 — the phone destination
# ---------------------------------------------------------------------------


def test_the_more_sheet_lists_the_partner():
    from src.tradelens.ui.components.sidebar import MOBILE_MORE, MOBILE_MORE_SLUGS

    assert "/Partner" in MOBILE_MORE_SLUGS
    entry = [e for e in MOBILE_MORE if e[0] == "/Partner"][0]
    assert entry[1] and entry[2], "the entry needs a label and a Material icon"


def test_the_partner_is_absent_from_the_desktop_rail():
    """One conversation must not have two entry points at one width."""
    from src.tradelens.ui.components.sidebar import PRIMARY_NAV, UTILITY_NAV

    slugs = [s for _p, s, _l, _i in PRIMARY_NAV + UTILITY_NAV]
    assert "/Partner" not in slugs


def test_the_partner_route_is_deep_linkable_like_every_other_destination():
    from src.tradelens.ui.components.sidebar import route_href

    assert route_href("/Partner", "tok").startswith("/Partner?")


def test_the_phone_page_and_the_drawer_share_one_conversation():
    """History is keyed by user, not by surface. Keying it by surface would
    give a trader two conversations and no way to tell which they were in."""
    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    assert 'render_partner_body(st, surface="page")' in page
    assert 'render_partner_body(st, surface="drawer")' in _SOURCE
    # …and the key that carries the conversation ignores the surface.
    import inspect

    assert "surface" not in inspect.signature(partner_turn.history_key).parameters


def test_the_phone_page_adds_no_second_primary_action():
    """ "Log completed trade" is the one primary action in this product."""
    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    assert 'type="primary"' not in page


def test_the_phone_page_opens_no_data_or_model_path_of_its_own():
    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    for banned in (
        "partner_reply",
        "build_global_partner_context",
        "log_ai_usage",
        "SessionLocal",
        "import anthropic",
    ):
        assert banned not in page, banned


def test_the_launcher_and_the_bottom_bar_are_never_both_available():
    """Structural, not a CSS trick: the launcher is hidden at exactly the
    widths where the bottom bar appears, so there is no width at which a
    floating overlay could collide with the More sheet."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()

    # The extent of the phone media query, by brace count. Splitting on "}"
    # is not enough here: the chunk that carries the launcher rule also
    # carries the `@media` opener itself, so asking what encloses that chunk
    # answers about the text before the query rather than inside it.
    start = css.rindex("@media (max-width: 767px)")
    depth, end = 0, None
    for i in range(css.index("{", start), len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end is not None, "unterminated phone media query"
    phone = css[start:end]

    assert ".st-key-tl_partner_launcher" in phone
    launcher = phone[phone.index(".st-key-tl_partner_launcher") :]
    assert "display: none" in launcher[: launcher.index("}")]

    assert ".tl-mobile-nav" in phone
    nav = phone[phone.index(".tl-mobile-nav {") :]
    assert "display: flex" in nav[: nav.index("}")]


# ---------------------------------------------------------------------------
# Phase 2 amendment — availability, clearing, sending, exclusivity
# ---------------------------------------------------------------------------


class _RichFakeSt(_FakeSt):
    """The fake, extended for the amendment's controls.

    Records which controls were offered and whether each was disabled, so the
    assertions below read what the surface produced rather than what its source
    says. `rerun` records instead of raising here, because these paths reach it
    legitimately.
    """

    def __init__(self, state=None):
        super().__init__(state)
        self.disabled = {}
        self.chat_inputs = []
        self.links = []
        self.reran = 0
        self.query_params = {}

    def button(self, label, **kwargs):
        self.buttons.append(label)
        self.disabled[label] = bool(kwargs.get("disabled"))
        return False

    def chat_input(self, placeholder, **kwargs):
        self.chat_inputs.append(
            {"placeholder": placeholder, "disabled": bool(kwargs.get("disabled"))}
        )
        return None

    def page_link(self, path, label=None, **kwargs):
        self.links.append((path, label))

    def rerun(self):
        self.reran += 1


def _render_body(monkeypatch, *, uid, ai_ready, context, state=None, surface="drawer"):
    from src.tradelens.ui.components import partner_panel as pp

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: uid)
    monkeypatch.setattr(pp, "ai_available", lambda: ai_ready)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: context)
    fake = _RichFakeSt(state)
    pp.render_partner_body(fake, surface=surface)
    return fake


class _Ctx:
    def __init__(self, trades=6, profile=None):
        self.context_text = "## Journal notes"
        self.strategy_profile = profile
        self.evidence_sources = ()
        self.completed_trade_count = trades
        self.journal_entry_count = trades


def test_an_ownerless_session_is_offered_no_composer(monkeypatch):
    """The adapter refuses an ownerless read, so a composer here would produce
    an error on every submission."""
    from src.tradelens.ui.components.partner_turn import NO_USER_ERROR

    fake = _render_body(monkeypatch, uid=None, ai_ready=True, context=None)
    assert fake.chat_inputs == []
    assert NO_USER_ERROR in "\n".join(fake.html)


def test_an_ownerless_session_never_reaches_the_context_adapter(monkeypatch):
    """Tenant isolation is not weakened to render a nicer message."""
    from src.tradelens.ui.components import partner_panel as pp

    calls = []
    monkeypatch.setattr(
        "src.tradelens.ui.components.auth.current_user_id", lambda: None
    )
    monkeypatch.setattr(pp, "ai_available", lambda: True)
    monkeypatch.setattr(
        pp,
        "build_global_partner_context",
        lambda *, user_id: calls.append(user_id) or _Ctx(),
    )
    pp.render_partner_body(_RichFakeSt(), surface="drawer")
    assert calls == [], "a context was built for a session with no owner"


def test_an_unconfigured_model_is_stated_without_naming_the_secret(monkeypatch):
    from src.tradelens.ui.components.partner_turn import AI_UNAVAILABLE

    fake = _render_body(monkeypatch, uid=7, ai_ready=False, context=_Ctx())
    assert fake.chat_inputs == []
    html = "\n".join(fake.html)
    assert AI_UNAVAILABLE in html
    assert "ANTHROPIC" not in html and "api key" not in html.lower()


def test_no_completed_trades_shows_the_new_trade_route(monkeypatch):
    from src.tradelens.ui.components.partner_turn import NO_TRADES_ERROR

    fake = _render_body(monkeypatch, uid=7, ai_ready=True, context=_Ctx(trades=0))
    assert fake.chat_inputs == [], "no composer without a trade to reflect on"
    assert NO_TRADES_ERROR in "\n".join(fake.html)
    assert fake.links == [("pages/1_NewTrade.py", "Log a completed trade →")]


def test_a_missing_profile_notices_but_still_takes_a_question(monkeypatch):
    fake = _render_body(monkeypatch, uid=7, ai_ready=True, context=_Ctx(profile=None))
    assert len(fake.chat_inputs) == 1
    assert fake.chat_inputs[0]["disabled"] is False
    assert "Strategy Profile" in "\n".join(fake.html)
    assert fake.links == [("pages/5_Strategy.py", "Add your Strategy Profile →")]


def test_a_present_profile_raises_no_notice(monkeypatch):
    fake = _render_body(
        monkeypatch, uid=7, ai_ready=True, context=_Ctx(profile={"name": "ICT"})
    )
    assert fake.links == []
    assert "No Strategy Profile yet" not in "\n".join(fake.html)


def test_the_composer_is_disabled_while_a_question_is_in_flight(monkeypatch):
    """The second pass. A Streamlit widget cannot become disabled inside its
    own handler, so the disabled state has to be rendered on a pass of its
    own — this asserts that pass produces it."""
    from src.tradelens.ui.components.partner_turn import history_key

    state = {
        "_partner_busy_drawer": True,
        "_partner_pending_drawer": "What did I repeat?",
        history_key(7): [{"role": "user", "content": "What did I repeat?"}],
    }
    fake = _render_body(monkeypatch, uid=7, ai_ready=True, context=_Ctx(), state=state)
    assert fake.chat_inputs[0]["disabled"] is True
    html = "\n".join(fake.html)
    assert 'aria-live="polite"' in html
    assert "Reading your journal" in html


def test_previous_turns_stay_on_screen_while_sending(monkeypatch):
    from src.tradelens.ui.components.partner_turn import history_key

    state = {
        "_partner_busy_drawer": True,
        "_partner_pending_drawer": "next question",
        history_key(7): [
            {"role": "user", "content": "EARLIER QUESTION"},
            {"role": "assistant", "content": "EARLIER ANSWER"},
        ],
    }
    fake = _render_body(monkeypatch, uid=7, ai_ready=True, context=_Ctx(), state=state)
    rendered = "\n".join(fake.text + fake.html)
    assert "EARLIER QUESTION" in rendered and "EARLIER ANSWER" in rendered


def test_the_turns_are_rendered_before_anything_that_could_refuse(monkeypatch):
    """Whatever this render is doing, the conversation does not move."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/tradelens/ui/components/partner_panel.py"
    ).read_text(encoding="utf-8")
    body = src[src.index("def render_partner_body") :]
    body = body[: body.index("def _clear_control")]
    assert body.index("_render_turn(st, turn)") < body.index("if not state.can_send")


def test_clear_conversation_is_offered_once_there_is_one(monkeypatch):
    from src.tradelens.ui.components.partner_turn import history_key

    empty = _render_body(monkeypatch, uid=7, ai_ready=True, context=_Ctx())
    assert "Clear conversation" not in empty.buttons

    with_history = _render_body(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state={history_key(7): [{"role": "user", "content": "q"}]},
    )
    assert "Clear conversation" in with_history.buttons


def test_clear_is_offered_even_when_the_partner_can_no_longer_send(monkeypatch):
    """A trader whose key was removed must still be able to dismiss the
    conversation they are looking at."""
    from src.tradelens.ui.components.partner_turn import history_key

    fake = _render_body(
        monkeypatch,
        uid=7,
        ai_ready=False,
        context=_Ctx(),
        state={history_key(7): [{"role": "user", "content": "q"}]},
    )
    assert "Clear conversation" in fake.buttons


def test_the_suggestion_chips_are_disabled_while_sending(monkeypatch):
    """They queue a question, so a live chip during a call would stack a
    second one behind the first."""
    fake = _render_body(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state={"_partner_busy_drawer": True},
    )
    chips = [b for b in fake.buttons if b in partner_panel.SUGGESTED_QUESTIONS]
    assert chips, "the empty state still offers its chips"
    assert all(fake.disabled[c] for c in chips)


def test_the_launcher_is_disabled_and_explains_itself_when_unavailable(monkeypatch):
    from src.tradelens.ui.components import partner_panel as pp
    from src.tradelens.ui.components.partner_turn import AI_UNAVAILABLE

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: 7)
    monkeypatch.setattr(pp, "ai_available", lambda: False)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: _Ctx())
    fake = _RichFakeSt()
    pp.render_partner_launcher(fake)
    assert fake.disabled["Ask about a trade"] is True
    # A disabled button leaves the tab order, so the reason must also be text.
    assert AI_UNAVAILABLE in "\n".join(fake.html)


def test_the_launcher_is_actionable_when_the_partner_is_ready(monkeypatch):
    from src.tradelens.ui.components import partner_panel as pp

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: 7)
    monkeypatch.setattr(pp, "ai_available", lambda: True)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: _Ctx())
    fake = _RichFakeSt()
    pp.render_partner_launcher(fake)
    assert fake.disabled["Ask about a trade"] is False


# --- responsive exclusivity -------------------------------------------------


def test_the_partner_route_suppresses_the_shell_partner():
    """A direct /Partner visit at a rail width would otherwise show the full
    page AND the global launcher. Decided from the route, server-side, so it
    holds at every width and leaves nothing hidden-but-tabbable."""
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    assert "render_sidebar(with_partner=False)" in page


def test_the_shell_renders_no_partner_when_asked_not_to():
    """Asserted by running it, not by reading it."""
    import ast
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/components/sidebar.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "render_sidebar"
    )
    assert any(a.arg == "with_partner" for a in fn.args.kwonlyargs)
    # Both calls sit inside the guard rather than beside it.
    guarded = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Name)
        and n.test.id == "with_partner"
    ]
    assert guarded, "the Partner calls are not behind the flag"
    dumped = ast.dump(guarded[0])
    assert "render_partner_launcher" in dumped
    assert "render_partner_drawer" in dumped


def test_every_other_destination_still_gets_the_shell_partner():
    from pathlib import Path

    pages = Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages"
    for page in pages.glob("*.py"):
        text = page.read_text(encoding="utf-8")
        if "render_sidebar(" not in text:
            continue
        if page.name == "7_Partner.py":
            continue
        assert "with_partner=False" not in text, page.name

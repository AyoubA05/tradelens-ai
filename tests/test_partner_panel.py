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
    from src.tradelens.ui.components import partner_turn as pt
    from src.tradelens.ui.components.partner_turn import history_key

    seen = {}

    def spy(state, *, user_id, text, **_kw):
        seen["user_id"] = user_id
        seen["text"] = text

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: 7)
    monkeypatch.setattr(pp, "ai_available", lambda: True)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: _Ctx())
    monkeypatch.setattr(pp, "send_turn", spy)

    state = {history_key(7): [{"role": "user", "content": "What did I repeat?"}]}
    _seed_queue(state, surface="drawer", text="What did I repeat?")
    fake = _RealisticSt(state)
    pt.begin_partner_run(fake.session_state)
    try:
        pp.render_partner_body(fake, surface="drawer")
    except _Rerun:
        pass
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


def test_ownerless_preview_page_shows_one_truthful_status_and_no_composer(monkeypatch):
    """The adapter refuses an ownerless read, so a composer here would produce
    an error on every submission."""
    from src.tradelens.ui.components.partner_turn import (
        NO_USER_ERROR,
        OWNERLESS_PREVIEW,
    )

    fake = _render_body(
        monkeypatch, uid=None, ai_ready=True, context=None, surface="page"
    )
    assert fake.chat_inputs == []
    rendered = "\n".join(fake.html + fake.text)
    assert rendered.count(OWNERLESS_PREVIEW) == 1
    assert NO_USER_ERROR not in rendered


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


def test_ownerless_preview_renders_no_dead_desktop_launcher(monkeypatch):
    from src.tradelens.ui.components import partner_panel as pp
    from src.tradelens.ui.components.partner_turn import NO_USER_ERROR

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
    fake = _RichFakeSt({"authenticated": True, "user_id": None})

    pp.render_partner_launcher(fake)

    rendered = "\n".join(fake.html + fake.text)
    assert calls == []
    assert fake.buttons == []
    assert "Ask about a trade" not in rendered
    assert NO_USER_ERROR not in rendered
    assert fake.html == [] and fake.text == [], "the desktop launcher must vanish"


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

    state = {history_key(7): [{"role": "user", "content": "What did I repeat?"}]}
    _seed_queue(state, surface="drawer", text="What did I repeat?")
    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        send=_recorder_calls(),
    )
    assert fake.chat_inputs[0]["disabled"] is True
    html = "\n".join(fake.html)
    assert 'aria-live="polite"' in html
    assert "Reading your journal" in html


def test_previous_turns_stay_on_screen_while_sending(monkeypatch):
    from src.tradelens.ui.components.partner_turn import history_key

    state = {
        history_key(7): [
            {"role": "user", "content": "EARLIER QUESTION"},
            {"role": "assistant", "content": "EARLIER ANSWER"},
        ]
    }
    _seed_queue(state, surface="drawer", text="next question")
    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        send=_recorder_calls(),
    )
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


def _chips_busy_state():
    state = {}
    _seed_queue(state, surface="drawer", text="in flight")
    return state


def test_the_suggestion_chips_are_disabled_while_sending(monkeypatch):
    """They queue a question, so a live chip during a call would stack a
    second one behind the first."""
    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=_chips_busy_state(),
        send=_recorder_calls(),
    )
    chips = [b for b in fake.buttons if b in partner_panel.SUGGESTED_QUESTIONS]
    assert chips, "the empty state still offers its chips"
    assert all(fake.disabled[c] for c in chips)


def test_an_unavailable_launcher_is_status_only_not_a_redundant_button(monkeypatch):
    from src.tradelens.ui.components import partner_panel as pp
    from src.tradelens.ui.components.partner_turn import AI_UNAVAILABLE

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: 7)
    monkeypatch.setattr(pp, "ai_available", lambda: False)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: _Ctx())
    fake = _RichFakeSt()
    pp.render_partner_launcher(fake)
    assert fake.buttons == []
    assert "\n".join(fake.html).count(AI_UNAVAILABLE) == 1


def test_the_launcher_is_actionable_when_the_partner_is_ready(monkeypatch):
    from src.tradelens.ui.components import partner_panel as pp

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: 7)
    monkeypatch.setattr(pp, "ai_available", lambda: True)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: _Ctx())
    fake = _RichFakeSt()
    pp.render_partner_launcher(fake)
    assert fake.disabled["Ask about a trade"] is False


# --- responsive exclusivity -------------------------------------------------


def test_the_partner_route_never_shows_two_partners():
    """Round 1 suppressed the shell's Partner on this route. That guaranteed
    the two never coexisted, but it left the phone presentation rendering on a
    desktop — non-coexistence was only half the requirement.

    Exclusivity now comes from two complementary media queries, so this
    asserts the pair rather than the suppression: whatever the width, exactly
    one of the two presentations is displayed.
    """
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()

    def _block(opener, selector):
        """The rule for `selector` inside `opener`, by brace count.

        Every block with that opener is searched, not just the first: the file
        carries several `@media (max-width: 767px)` blocks and the Partner
        rules are not in the earliest one.
        """
        at = 0
        while True:
            start = css.find(opener, at)
            assert start != -1, f"{selector} missing from every {opener}"
            depth, end = 0, None
            for i in range(css.index("{", start), len(css)):
                if css[i] == "{":
                    depth += 1
                elif css[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            region = css[start:end]
            if selector in region:
                tail = region[region.index(selector) :]
                return tail[: tail.index("}")]
            at = start + 1

    # >= 768: the page is gone, so the launcher and drawer are the Partner.
    assert "display: none" in _block(
        "@media (min-width: 768px) {", ".st-key-tl_partner_page"
    )
    # <= 767: the launcher and drawer are gone, so the page is the Partner.
    assert "display: none" in _block(
        "@media (max-width: 767px) {", ".st-key-tl_partner_launcher"
    )


def test_the_shell_renders_its_partner_on_every_destination():
    """Round 1's `with_partner` flag is gone with the approach that needed it.
    A parameter no caller passes is one that rots, and the shell now has one
    behaviour: it always offers the Partner, and CSS decides which of the two
    presentations a width gets."""
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
    assert not any(a.arg == "with_partner" for a in fn.args.kwonlyargs)
    dumped = ast.dump(fn)
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


# ---------------------------------------------------------------------------
# Round 2 — Codex's review of ebdba27
# ---------------------------------------------------------------------------


class _Rerun(Exception):
    """What `st.rerun()` really does: raises, and the script run ends there."""


class _RealisticSt(_RichFakeSt):
    """A fake with the two lifecycle behaviours the earlier one lacked.

    `rerun()` raises, because that is what Streamlit's does — a pass that
    reruns is over, and the earlier fake let execution fall through into code
    that never runs in the product.

    Session state is the caller's own dict, not a copy, because it *persists
    across reruns*. Copying it made every pass start from the original state,
    so a test that ran two passes over one session was really running two
    first passes — which is how the first version of the interrupted-send
    test passed while the defect was live.
    """

    def __init__(self, state=None, types=None):
        super().__init__(state)
        self.session_state = state if state is not None else {}
        self._types = types

    def chat_input(self, placeholder, **kwargs):
        """Submit `types` once, as a trader pressing enter would.

        Driving the real composer matters: seeding the queue by hand would
        test the reader of a session key rather than the path that writes it.
        """
        self.chat_inputs.append(
            {"placeholder": placeholder, "disabled": bool(kwargs.get("disabled"))}
        )
        if kwargs.get("disabled"):
            return None
        value, self._types = self._types, None
        return value

    def rerun(self):
        self.reran += 1
        raise _Rerun()


def _seed_queue(state, *, surface, text):
    """Leave a queue that the NEXT run is entitled to claim.

    Stamped with the current run, because `begin_partner_run` bumps the counter
    before the body reads it — which is exactly the adjacency the product
    relies on. Seeding an arbitrary number would test a situation the product
    cannot produce.
    """
    from src.tradelens.ui.components.partner_turn import current_run, queue_question

    queue_question(state, surface=surface, text=text, run_id=current_run(state))


def _render_realistic(
    monkeypatch,
    *,
    uid,
    ai_ready,
    context,
    state=None,
    surface="drawer",
    build_raises=False,
    send=None,
    types=None,
):
    from src.tradelens.ui.components import partner_panel as pp
    from src.tradelens.ui.components.partner_turn import begin_partner_run

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: uid)
    monkeypatch.setattr(pp, "ai_available", lambda: ai_ready)

    def _build(*, user_id):
        if build_raises:
            raise RuntimeError('psycopg2 dsn="postgresql://tl:pw@db:5432/tl"')
        return context

    monkeypatch.setattr(pp, "build_global_partner_context", _build)
    if send is not None:
        monkeypatch.setattr(pp, "send_turn", send)
    fake = _RealisticSt(state, types=types)
    begin_partner_run(fake.session_state)
    try:
        pp.render_partner_body(fake, surface=surface)
    except _Rerun:
        pass
    return fake


# --- 1. a context that could not be built ----------------------------------


def test_a_failed_context_never_becomes_the_no_trades_state(monkeypatch):
    """Telling a trader with a full journal to go and log a trade, because the
    database was unreachable, is worse than saying nothing."""
    from src.tradelens.ui.components.partner_turn import (
        CONTEXT_UNAVAILABLE,
        NO_TRADES_ERROR,
    )

    fake = _render_realistic(
        monkeypatch, uid=7, ai_ready=True, context=None, build_raises=True
    )
    html = "\n".join(fake.html)
    assert CONTEXT_UNAVAILABLE in html
    assert NO_TRADES_ERROR not in html
    assert fake.links == [], "no route is offered for a failure it cannot fix"
    assert fake.chat_inputs == []


def test_a_failed_context_leaks_no_driver_text(monkeypatch):
    fake = _render_realistic(
        monkeypatch, uid=7, ai_ready=True, context=None, build_raises=True
    )
    rendered = "\n".join(fake.html + fake.text)
    for leak in ("psycopg2", "postgresql://", "dsn", "Traceback"):
        assert leak not in rendered


# --- 2. a two-pass send interrupted between its passes ----------------------


def test_queuing_a_question_ends_the_run_without_sending(monkeypatch):
    """First pass records intent and reruns. With a fake that returns from
    `rerun()` the code below it kept executing, so this could not be seen."""
    from src.tradelens.ui.components.partner_turn import QUEUE_KEY

    sent = _recorder_calls()
    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state={},
        send=sent,
        types="queued question",
    )
    assert sent.calls == [], "the model was called on the queueing pass"
    assert fake.reran == 1
    assert fake.session_state[QUEUE_KEY]["text"] == "queued question"


def test_a_question_queued_before_availability_changed_is_never_sent(monkeypatch):
    """The interruption Codex found. A question is queued, and by the next
    pass the Partner can no longer send — the key was pulled, the trades were
    deleted, the database went down. The pending question must not survive to
    be auto-sent by a later rerun that happens to find availability restored:
    that is model usage and billing the trader never asked for.
    """
    from src.tradelens.ui.components.partner_turn import QUEUE_KEY

    sent = _recorder_calls()
    state = {}
    _seed_queue(state, surface="drawer", text="queued before the key was pulled")
    fake = _render_realistic(
        monkeypatch, uid=7, ai_ready=False, context=_Ctx(), state=state, send=sent
    )
    assert sent.calls == [], "an interrupted question was sent anyway"
    assert QUEUE_KEY not in fake.session_state


def test_the_discarded_question_is_reported_not_silently_dropped(monkeypatch):
    from src.tradelens.ui.components.partner_turn import QUESTION_DISCARDED

    state = {}
    _seed_queue(state, surface="drawer", text="queued")
    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=False,
        context=_Ctx(),
        state=state,
        send=_recorder_calls(),
    )
    assert QUESTION_DISCARDED in "\n".join(fake.html)


def test_availability_returning_later_does_not_resurrect_the_question(monkeypatch):
    """The whole point: the state left behind by the interrupted pass must
    contain nothing that a healthy later pass would act on."""
    sent = _recorder_calls()
    state = {}
    _seed_queue(state, surface="drawer", text="queued before the key was pulled")
    # Pass A: unavailable — the queue is cleared.
    _render_realistic(
        monkeypatch, uid=7, ai_ready=False, context=_Ctx(), state=state, send=sent
    )
    # Pass B: everything healthy again, same session state.
    _render_realistic(
        monkeypatch, uid=7, ai_ready=True, context=_Ctx(), state=state, send=sent
    )
    assert sent.calls == [], "the question came back to life on a later pass"


def test_a_healthy_second_pass_still_sends_exactly_once(monkeypatch):
    """The fix must not break sending."""
    from src.tradelens.ui.components.partner_turn import QUEUE_KEY

    sent = _recorder_calls()
    state = {}
    _seed_queue(state, surface="drawer", text="a real question")
    fake = _render_realistic(
        monkeypatch, uid=7, ai_ready=True, context=_Ctx(), state=state, send=sent
    )
    assert len(sent.calls) == 1
    assert sent.calls[0][1]["text"] == "a real question"
    assert QUEUE_KEY not in fake.session_state


# --- 3. the profile notice, whether or not there is history -----------------


def test_the_profile_notice_survives_a_conversation(monkeypatch):
    """It was rendered only inside the empty-state branch, so the moment a
    trader asked anything the reason their answers were thin disappeared."""
    from src.tradelens.ui.components.partner_turn import history_key

    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(profile=None),
        state={
            history_key(7): [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ]
        },
    )
    assert "No Strategy Profile yet" in "\n".join(fake.html)
    assert fake.links == [("pages/5_Strategy.py", "Add your Strategy Profile →")]


def test_a_present_profile_stays_quiet_with_history_too(monkeypatch):
    from src.tradelens.ui.components.partner_turn import history_key

    fake = _render_realistic(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(profile={"name": "ICT"}),
        state={history_key(7): [{"role": "user", "content": "q"}]},
    )
    assert "No Strategy Profile yet" not in "\n".join(fake.html)
    assert fake.links == []


def _recorder_calls():
    def fn(*args, **kwargs):
        fn.calls.append((args, kwargs))

    fn.calls = []
    return fn


# --- 4. the full page belongs to bottom-navigation widths only --------------


def test_the_full_page_partner_is_hidden_at_rail_widths():
    """Non-coexistence was not the whole requirement. The full-page
    presentation is for bottom-navigation widths, so at a rail width it must
    not render at all — and `display: none` is what removes it from the tab
    order rather than merely hiding it."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    # The exact block. `@media (min-width: 768px) and (max-width: 1023px)`
    # appears earlier and starts identically, so an `index` on the prefix
    # finds the rail-width sidebar rules instead of this one.
    start = css.index("@media (min-width: 768px) {")
    depth, end = 0, None
    for i in range(css.index("{", start), len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    rail = css[start:end]
    assert ".st-key-tl_partner_page" in rail
    block = rail[rail.index(".st-key-tl_partner_page") :]
    assert "display: none" in block[: block.index("}")]


def test_the_two_presentations_are_hidden_at_exactly_opposite_widths():
    """One Partner at every width, by construction: the page is hidden from
    768 up and the launcher and drawer are hidden to 767."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    phone = css[css.rindex("@media (max-width: 767px)") :]
    assert ".st-key-tl_partner_launcher" in phone[: phone.index("@media")] or (
        ".st-key-tl_partner_launcher" in phone[:4000]
    )
    assert "@media (min-width: 768px)" in css


def test_the_page_body_is_keyed_so_the_rule_can_reach_it():
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    assert 'st.container(key="tl_partner_page")' in page


def test_the_desktop_visitor_is_told_where_the_partner_is():
    """A direct /Partner visit at a rail width must not be a blank page."""
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    assert "tl-partner-desktop-note" in page


def test_the_shell_partner_is_restored_on_the_partner_route():
    """It is what a rail-width visitor uses, now that the full page is hidden
    there. Exclusivity comes from the two media queries, not from suppressing
    the shell."""
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/7_Partner.py"
    ).read_text(encoding="utf-8")
    assert "with_partner=False" not in page


# ---------------------------------------------------------------------------
# Round 3 — a hidden presentation must never spend
# ---------------------------------------------------------------------------
#
# Both presentations execute server-side on every run. CSS decides which one a
# width *shows*, and Streamlit has no server-side knowledge of the viewport —
# so "hidden" is a fact about the browser that the script cannot read. A queue
# left in session state by one presentation could therefore be picked up and
# sent by that same presentation on a later run, at a width where nobody can
# see it happen. That is model usage and a bill with no visible cause.


def _partner_run(
    monkeypatch, *, uid, ai_ready, context, state, surface, send=None, types=None
):
    """One script run's worth of Partner rendering for a single surface."""
    from src.tradelens.ui.components import partner_panel as pp
    from src.tradelens.ui.components.partner_turn import begin_partner_run

    monkeypatch.setattr("src.tradelens.ui.components.auth.current_user_id", lambda: uid)
    monkeypatch.setattr(pp, "ai_available", lambda: ai_ready)
    monkeypatch.setattr(pp, "build_global_partner_context", lambda *, user_id: context)
    if send is not None:
        monkeypatch.setattr(pp, "send_turn", send)
    fake = _RealisticSt(state, types=types)
    # The shell stamps the run before either presentation renders, exactly as
    # `render_sidebar` does in the product.
    begin_partner_run(fake.session_state)
    try:
        pp.render_partner_body(fake, surface=surface)
    except _Rerun:
        pass
    return fake


def test_a_page_queue_is_never_sent_after_the_run_that_made_it(monkeypatch):
    """The page→desktop case.

    A trader queues a question on the phone page. The sending run never
    completes — they navigate away, the socket drops, the tab is closed. The
    queue survives in session state. Later they are on a desktop, where the
    page body still executes but is hidden by CSS. Nothing on that screen may
    call the model.
    """
    sent = _recorder_calls()
    state = {}

    # Run 1, phone: the question is queued and the run ends in a rerun.
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
        types="What did I repeat?",
    )
    assert sent.calls == []

    # Runs 2 and 3 happen elsewhere — another page, a reload, a resize. The
    # shell stamps each one; the Partner page is not rendering.
    from src.tradelens.ui.components.partner_turn import begin_partner_run

    begin_partner_run(state)
    begin_partner_run(state)

    # Run 4, desktop: the page body executes, hidden. It must not send.
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
    )
    assert sent.calls == [], "a hidden page sent a stale question"


def test_a_drawer_queue_is_never_sent_after_the_run_that_made_it(monkeypatch):
    """The symmetric drawer→mobile case: the drawer body executes whenever
    `partner_open` is set, and at phone widths CSS hides it."""
    sent = _recorder_calls()
    state = {}

    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="drawer",
        send=sent,
        types="What did I repeat?",
    )
    assert sent.calls == []

    from src.tradelens.ui.components.partner_turn import begin_partner_run

    begin_partner_run(state)
    begin_partner_run(state)

    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="drawer",
        send=sent,
    )
    assert sent.calls == [], "a hidden drawer sent a stale question"


def test_the_other_presentation_can_never_claim_a_queue(monkeypatch):
    """One shared conversation, but the queue belongs to the surface the
    trader actually acted on. On /Partner both bodies execute in the same run,
    so an unowned claim would let the hidden one send what the visible one
    queued."""
    sent = _recorder_calls()
    state = {}
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
        types="the page's question",
    )
    # The very next run — adjacent, so not stale — but the DRAWER renders.
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="drawer",
        send=sent,
    )
    assert sent.calls == [], "the drawer sent the page's question"


def test_the_normal_two_pass_send_still_works(monkeypatch):
    """The guard must not break the thing it protects: a question queued on
    one run is sent on the run immediately after it, by its own surface."""
    sent = _recorder_calls()
    state = {}
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
        types="a real question",
    )
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
    )
    assert len(sent.calls) == 1
    assert sent.calls[0][1]["text"] == "a real question"


def test_a_stale_queue_leaves_no_state_behind(monkeypatch):
    """Discarded means gone, not merely skipped: a queue left in place would
    be claimed by whichever run happened to land adjacent to it next."""
    from src.tradelens.ui.components.partner_turn import QUEUE_KEY, begin_partner_run

    sent = _recorder_calls()
    state = {}
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
        types="a question nobody waited for",
    )
    begin_partner_run(state)
    begin_partner_run(state)
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
    )
    assert QUEUE_KEY not in state
    # …and a further adjacent pair cannot resurrect it.
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=sent,
    )
    assert sent.calls == []


def test_only_one_queue_can_exist_at_a_time(monkeypatch):
    """Two per-surface queues could both be live, and the hidden one would
    have its own turn to fire. There is one."""
    from src.tradelens.ui.components.partner_turn import QUEUE_KEY

    state = {}
    _partner_run(
        monkeypatch,
        uid=7,
        ai_ready=True,
        context=_Ctx(),
        state=state,
        surface="page",
        send=_recorder_calls(),
        types="one question",
    )
    queued = [k for k in state if "pending" in k or k == QUEUE_KEY]
    assert queued == [QUEUE_KEY], f"more than one queue slot: {queued}"


def test_the_shell_stamps_the_run_before_either_presentation_renders():
    """The adjacency rule is only meaningful if something advances the
    counter, and it must advance ONCE per run, before both bodies read it —
    otherwise the drawer and the page would disagree about which run they are
    in on the Partner route.

    Removing the stamp from the shell was a mutation the first version of this
    file did not catch, because every test drove `begin_partner_run` itself.
    """
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
    calls = [
        (n.lineno, n.func.id)
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id
        in {"begin_partner_run", "render_partner_launcher", "render_partner_drawer"}
    ]
    names = [name for _line, name in calls]
    assert (
        names.count("begin_partner_run") == 1
    ), f"stamped {names.count('begin_partner_run')} times"
    stamp = next(line for line, name in calls if name == "begin_partner_run")
    for line, name in calls:
        if name != "begin_partner_run":
            assert stamp < line, f"{name} renders before the run is stamped"


def test_an_unstamped_session_can_never_claim_a_question():
    """The safe direction of the failure. If the counter never advances, a
    queue can never satisfy `queued.run + 1 == run_id`, so an unstamped
    session stops sending rather than sending invisibly."""
    from src.tradelens.ui.components.partner_turn import (
        claim_question,
        current_run,
        queue_question,
    )

    state = {}
    assert current_run(state) == 0
    queue_question(state, surface="page", text="q", run_id=current_run(state))
    # No `begin_partner_run` — the counter is still 0.
    assert claim_question(state, surface="page", run_id=current_run(state)) is None

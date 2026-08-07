"""
Static-source polish checks for all 9 Streamlit pages (Phase 3, week6-d3).

These enforce the design-system rules by grepping each page's source — fast,
deterministic, and self-documenting so future sessions can extend them. They do
NOT import the pages (pages run Streamlit at import time); they read source text.
"""

import re
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"

# Session A: only the active (non-archived) pages are linted. Home/TradeDetail/
# Calendar/Weekly/AI Partner now live in pages/_archive/ (Calendar + Weekly are
# Analytics tabs); they re-enter the app in Session B/C.
ALL_PAGES = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    "9_Settings.py",
]

# Active pages that make AI calls. Pattern detection + the Weekly Review now live
# on the merged Insights & Review page (Analytics is pure analytics again).
AI_PAGES = [
    "6_Insights.py",
]

# Empty-state phrasing that must live in empty_state(), never a raw st.info().
# Extend this list as new empty-state copy appears.
EMPTY_STATE_PHRASES = [
    "no trades",
    "no data",
    "no results",
    "nothing here",
    "no entries",
]

# Emoji blocks (pictographs + dingbats/misc symbols + variation selectors).
# Typographic arrows are intentionally excluded — they are not icon emoji.
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0000fe00-\U0000fe0f"
    "\U0001f000-\U0001f0ff"
    "]"
)

_HEADING_CALL = re.compile(r"st\.(?:title|header|subheader)\((.*?)\)", re.DOTALL)
_PAGE_ICON = re.compile(r"page_icon\s*=\s*[\"']([^\"']*)[\"']")
_ST_INFO = re.compile(r"st\.info\((.*?)\)", re.DOTALL)


def _src(page: str) -> str:
    return (PAGES_DIR / page).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Constraint 1 — exactly one inject_css() call per page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_exactly_one_inject_css(page):
    assert (
        _src(page).count("inject_css()") == 1
    ), f"{page}: expected exactly one inject_css() call"


# ---------------------------------------------------------------------------
# Constraint 4 — no bare st.error / st.success in the UI layer (use toasts)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_error(page):
    # icon='✕' (U+2715) looks right but fails Streamlit's validate_icon_or_emoji;
    # use '❌' (U+274C) — see test_toast_icons.py for the full story.
    assert "st.error(" not in _src(page), f"{page}: use st.toast(msg, icon='❌')"


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_success(page):
    # icon='✓' (U+2713) looks right but fails Streamlit's validate_icon_or_emoji;
    # use '✅' (U+2705) — see test_toast_icons.py for the full story.
    assert "st.success(" not in _src(page), f"{page}: use st.toast(msg, icon='✅')"


# ---------------------------------------------------------------------------
# Bare-except guard — a bare `except:` swallows stack traces into blank widgets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_exception(page):
    for i, line in enumerate(_src(page).splitlines(), 1):
        assert not re.match(
            r"\s*except\s*:", line
        ), f"{page}:{i}: bare 'except:' — catch a specific exception and toast it"


# ---------------------------------------------------------------------------
# Constraint 5 — empty states go through empty_state(), not st.info()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_emptystate_st_info(page):
    for call in _ST_INFO.findall(_src(page)):
        low = call.lower()
        for phrase in EMPTY_STATE_PHRASES:
            assert phrase not in low, (
                f"{page}: st.info() contains empty-state phrase {phrase!r} — "
                "use empty_state() instead"
            )


# ---------------------------------------------------------------------------
# No emoji in page headings or page_icon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_emoji_in_headings(page):
    src = _src(page)
    for heading in _HEADING_CALL.findall(src):
        assert not _EMOJI.search(heading), f"{page}: emoji in heading: {heading!r}"
    for icon in _PAGE_ICON.findall(src):
        assert not _EMOJI.search(icon), f"{page}: emoji page_icon: {icon!r}"


# ---------------------------------------------------------------------------
# AI spinners must NOT leak a model brand name (Session A, Section 3).
# Copy stays generic ("AI reviews your chart"), never "Fable 5".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", AI_PAGES)
def test_ai_spinner_has_no_model_brand(page):
    """Whatever the waiting state says, it names the product, not the model.

    AI Reviews now waits with a geometry-preserving skeleton rather than a
    spinner, so a page may legitimately have no st.spinner at all.
    """
    src = _src(page)
    spinners = re.findall(r"st\.spinner\(\s*[\"'](.+?)[\"']", src)
    assert (
        spinners or "render_note_skeleton" in src
    ), f"{page}: expected visible loading feedback"
    for text in spinners:
        low = text.lower()
        assert "fable" not in low, f"{page}: spinner leaks a model brand: {text!r}"
        assert "claude" not in low, f"{page}: spinner leaks a model brand: {text!r}"


# ---------------------------------------------------------------------------
# Constraint 2 — emotion picker writes the existing 3 columns, no new ones
# ---------------------------------------------------------------------------


def test_emotion_picker_uses_existing_columns():
    src = _src("1_NewTrade.py")
    for col in ("emotions_before", "emotions_during", "emotions_after"):
        assert col in src, f"emotion column {col} missing from New Trade form"


def test_psychology_step_has_process_notes_field():
    """Item 8: dedicated 'What happened during this trade?' process-notes field."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "ui"
        / "pages"
        / "1_NewTrade.py"
    ).read_text(encoding="utf-8")
    assert "What happened during this trade?" in src
    assert "nt_process_notes" in src
    assert '"trade_process_notes": process_notes' in src  # saved as its own field
    # The emotional field remains a SEPARATE field with its own key. Its label
    # was shortened ("How were you feeling during this trade?" → "How were you
    # feeling?") — the surrounding step already says it is about this trade.
    assert "nt_mindset" in src
    assert "How were you feeling?" in src
    assert '"emotions_during": final_during' in src


# ---------------------------------------------------------------------------
# SP4 Phase B — loading feedback on AI paths
# ---------------------------------------------------------------------------

_COMPONENTS_DIR = PAGES_DIR.parent / "components"

# The modules that OWN an AI call each show a spinner at the call site.
# 1_NewTrade.py itself makes no direct AI call (its AI runs through
# ai_autofill_review, which is asserted here), so it is deliberately absent.
_AI_CALL_OWNERS = [
    PAGES_DIR / "6_Insights.py",
    _COMPONENTS_DIR / "ai_autofill_review.py",
    _COMPONENTS_DIR / "screenshot_analyzer.py",
]


@pytest.mark.parametrize("path", _AI_CALL_OWNERS, ids=lambda p: p.name)
def test_ai_call_owners_show_loading_feedback(path):
    """SP4 Phase B: AI calls take seconds — every module that makes one must
    show progress rather than freezing the pane with no feedback.

    A skeleton counts, and on AI Reviews it is the better answer: it holds
    the note's geometry, so the page does not jump when the review lands.
    """
    src = path.read_text(encoding="utf-8")
    assert (
        "st.spinner" in src or "render_note_skeleton" in src
    ), f"{path.name}: AI call path needs visible loading feedback"


# ---------------------------------------------------------------------------
# Constraint — New Trade shows exactly one progress system
# ---------------------------------------------------------------------------


def test_new_trade_has_one_progress_component():
    """One position indicator, not two.

    Tabs were the surviving system while every step's body had to render on
    every run to keep the save payload defined. The wizard reads its values
    from session state instead, so a real step rail can replace them — and
    tabs must not come back alongside it.
    """
    src = _src("1_NewTrade.py")
    assert src.count("st.tabs(") == 0, "tabs render every step at once"
    assert src.count("render_step_indicator(") == 1


def test_new_trade_renders_only_the_active_step():
    """A wizard that renders all five bodies is a long form with a rail on
    top of it."""
    src = _src("1_NewTrade.py")
    assert "_STEP_BODIES[STEP]()" in src
    assert "current_step(st.session_state)" in src


def test_new_trade_steps_use_the_approved_names():
    from src.tradelens.ui.components.trade_wizard import WIZARD_STEPS

    assert WIZARD_STEPS == (
        "Screenshot",
        "Context",
        "Execution",
        "Reflection",
        "Review",
    )


def test_new_trade_keeps_the_draft_alive_across_steps():
    """Streamlit drops the state of any widget it did not render this run.
    Without keep_alive, moving to step 3 would silently empty steps 1-2."""
    src = _src("1_NewTrade.py")
    assert "keep_alive(st.session_state)" in src
    # …and it must run before the first widget is created.
    assert src.index("keep_alive(st.session_state)") < src.index("st.selectbox(")


def test_new_trade_reads_its_payload_from_session_state():
    """Only one step renders, so widget return values cannot be the source
    of truth — four of the five steps never ran."""
    src = _src("1_NewTrade.py")
    for key in ("nt_asset_select", "nt_pnl", "nt_mindset", "nt_setup"):
        assert f'st.session_state.get("{key}")' in src or f'_raw("{key}")' in src


def test_new_trade_has_a_sticky_action_bar():
    src = _src("1_NewTrade.py")
    assert 'st.container(key="tl_wizard_bar")' in src
    assert "← Back" in src and "Continue →" in src
    assert "Save completed trade" in src
    # "kept", not "saved" — beside a Save button, the other wording reads as
    # though the trade were already in the journal. Scoped to code: a comment
    # naming the retired string is documentation, not a use.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert "Draft kept" in code
    assert "Draft saved" not in code


def test_new_trade_validates_on_navigation_not_on_keystroke():
    src = _src("1_NewTrade.py")
    assert "def _go_next()" in src
    assert "missing_required_fields(STEP, _FIELD_VALUES)" in src


def test_new_trade_reset_is_scoped_to_wizard_keys():
    """Clearing the whole session after a save would sign the trader out."""
    src = _src("1_NewTrade.py")
    assert "reset_wizard_state(st.session_state)" in src
    assert 'startswith("nt_")' not in src, "hand-rolled key sweep replaced"


def test_reflection_fields_never_block_the_save():
    from src.tradelens.ui.components.trade_wizard import (
        FIRST_STEP,
        LAST_STEP,
        required_fields_for_step,
    )

    for step in range(FIRST_STEP, LAST_STEP + 1):
        for optional in ("mindset", "did_well", "do_better", "process_notes"):
            assert optional not in required_fields_for_step(step)


def test_review_hides_blank_rows_instead_of_listing_them():
    """Review & Save must not repeat 'Not entered yet' down the page.

    Blank optional rows collapse to one per-section count; a section with
    nothing filled in is dropped entirely.
    """
    src = _src("1_NewTrade.py")
    assert "value != _NOT_ENTERED" in src
    assert "optional field" in src


# ---------------------------------------------------------------------------
# Constraint — solid teal is reserved for primary actions
# ---------------------------------------------------------------------------

# (page, key fragment) pairs for controls that must NOT read as the primary
# action: resets, regenerates, retries, and destructive controls.
SECONDARY_CONTROLS = [
    ("2_Trades.py", "secondary_jf_clear"),
    ("2_Trades.py", "secondary_delete_btn"),
    ("6_Insights.py", "secondary_ins_wk_regen"),
    ("6_Insights.py", "secondary_ins_wk_retry"),
    ("6_Insights.py", "secondary_ins_dbf_regen"),
    ("6_Insights.py", "secondary_ins_dbf_retry"),
]


@pytest.mark.parametrize(("page", "key"), SECONDARY_CONTROLS)
def test_secondary_controls_use_the_secondary_key_prefix(page, key):
    """The CSS is scoped by widget key, so the key IS the styling contract."""
    assert f'key="{key}"' in _src(page)


def test_design_system_styles_the_secondary_key_prefix():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    assert "st-key-secondary_" in css
    assert "background: transparent" in css


def test_save_trade_remains_primary():
    """Reserving teal must not demote the action that completes the task."""
    assert 'type="primary", key="edit_save"' in _src("2_Trades.py")
    assert "secondary_edit_save" not in _src("2_Trades.py")


def test_sidebar_does_not_cover_the_dashboard_on_a_phone():
    """An expanded sidebar at 390px hides the entire dashboard.

    "auto" keeps it open on desktop and collapsed on small screens, so a
    mobile visitor's first view is their trades rather than navigation.
    """
    app = (PAGES_DIR.parent / "app.py").read_text(encoding="utf-8")
    assert 'initial_sidebar_state="auto"' in app
    assert 'initial_sidebar_state="expanded"' not in app


# ---------------------------------------------------------------------------
# Marketing screenshots (Task 11)
#
# The four in-app stills are the only view of the product a prospective user
# gets before signing up. These guard the contract between the capture
# script, the files on disk, and the markup that declares their box.
# ---------------------------------------------------------------------------

_SITE = Path(__file__).resolve().parents[1] / "site"
_CAPTURE = (
    Path(__file__).resolve().parents[1] / "scripts" / "capture_app_screenshots.py"
)


def _index_html() -> str:
    return (_SITE / "index.html").read_text(encoding="utf-8")


def test_capture_script_targets_the_paths_the_site_actually_references():
    """A capture written to a path nothing references refreshes nothing."""
    from scripts.capture_app_screenshots import CAPTURES

    html = _index_html()
    for _name, _route, out_path, _w, _h, _s in CAPTURES:
        asset = out_path.split("site/")[-1]
        assert asset in html, f"{asset} is not referenced by the marketing site"


def test_marketing_screenshots_match_their_declared_dimensions():
    """width/height reserve the image's box before it loads. A file whose
    real size disagrees changes the page's aspect ratio as it arrives —
    exactly the layout shift those attributes exist to prevent."""
    from PIL import Image

    from scripts.capture_app_screenshots import CAPTURES

    html = _index_html()
    for name, _route, out_path, width, height, _scale in CAPTURES:
        path = Path(__file__).resolve().parents[1] / out_path
        assert path.exists(), f"{name}: {out_path} is missing"
        with Image.open(path) as image:
            assert image.format == "WEBP", f"{name}: {image.format}, expected WEBP"
            assert image.size == (width, height), (
                f"{name}: file is {image.size}, capture script declares "
                f"{(width, height)}"
            )
        asset = out_path.split("site/")[-1]
        for tag in re.findall(r"<img[^>]*>", html, re.S):
            if asset not in tag:
                continue
            declared_w = re.search(r'width="(\d+)"', tag)
            declared_h = re.search(r'height="(\d+)"', tag)
            assert declared_w and declared_h, f"{asset}: no width/height attributes"
            assert (int(declared_w.group(1)), int(declared_h.group(1))) == (
                width,
                height,
            ), f"{asset}: markup declares a different box than the file"


def test_every_product_screenshot_is_lazy_and_described():
    """Below-the-fold stills must not block the first paint, and an image
    with no alt text is invisible to a screen reader."""
    html = _index_html()
    for tag in re.findall(r"<img[^>]*>", html, re.S):
        if "shot-" not in tag:
            continue
        assert 'loading="lazy"' in tag, f"not lazy: {tag[:90]}"
        alt = re.search(r'alt="([^"]*)"', tag)
        assert alt, f"no alt attribute: {tag[:90]}"
        text = alt.group(1).strip()
        # Descriptive, not a filename and not a bare label: it must name
        # what is ON the screen, so a reader who cannot see the image
        # learns what a sighted reader does.
        assert len(text) > 30, f"alt text too thin to describe a screen: {text!r}"
        assert "shot-" not in text and ".webp" not in text, f"filename as alt: {text!r}"


def test_the_capture_script_verifies_what_it_wrote():
    """A capture run that reports success without re-reading the files is
    how a 0-byte or wrongly-sized asset ships."""
    src = _CAPTURE.read_text(encoding="utf-8")
    assert "def verify(" in src
    assert "prefers-reduced-motion" in src, "stills must not catch an animation"
    assert "stException" in src, "a page that errored must not be published"


def test_the_capture_never_writes_to_the_development_database():
    """A marketing shot needs a configured strategy and sample trades, and
    creating those is a write. It goes into a throwaway SQLite file, never
    whatever database the developer happens to be working in."""
    from scripts import capture_app_screenshots as capture

    src = _CAPTURE.read_text(encoding="utf-8")
    assert "def seed_capture_db(" in src
    assert 'os.environ["DATABASE_URL"]' in src
    assert "tempfile.mkdtemp" in src
    assert capture.CAPTURE_DIR_PREFIX.startswith("tradelens-capture")
    # …and there is a documented, ownership-scoped way to remove one again.
    # Deletion behaviour itself is covered in tests/test_capture_cleanup.py.
    assert "def clean_capture_dir(" in src
    assert "def clean_capture_dirs(" not in src, "the temp-directory sweep is back"
    assert "--clean" in src


def test_the_capture_fails_when_the_expected_strategy_is_absent():
    """Better to stop than to publish four screenshots of an empty product.
    Checked twice: after seeding, and against the RUNNING app, because a
    correctly seeded database the app was never pointed at still yields
    empty shots."""
    src = _CAPTURE.read_text(encoding="utf-8")
    assert "capture db has no active strategy after seeding" in src
    assert "capture db has no sample trades after seeding" in src
    assert "_assert_app_shows_the_seeded_strategy" in src
    assert "No active strategy" in src


def test_the_capture_never_prints_the_session_token():
    """The token grants a session. Echoing it into a terminal, a CI log or a
    shell scrollback is handing out access to the account."""
    import ast

    tree = ast.parse(_CAPTURE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"):
            continue
        printed = ast.dump(node)
        assert "token" not in printed.lower(), ast.unparse(node)


def test_the_starter_playbook_has_exactly_one_definition():
    """The capture reads it out of the page that owns it rather than
    keeping a second copy that would drift."""
    from scripts.capture_app_screenshots import starter_playbook

    page = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "ui"
        / "pages"
        / "5_Strategy.py"
    ).read_text(encoding="utf-8")
    assert page.count("STARTER_TEMPLATE = {") == 1
    playbook = starter_playbook()
    assert playbook["name"] == "ICT/SMC Day Trading"
    # every playbook section is filled, which is what "6 of 6" depends on
    for field in ("entry_rules", "stop_rules", "risk_rules", "common_mistakes"):
        assert playbook[field].strip()


# --- Task 9, the plan's tests transcribed verbatim to record their result ---


def test_the_dataframe_toolbar_controls_are_lifted_to_the_target_floor():
    """Live preflight measured these at 22.4x22.4 CSS px at 1440."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    toolbar = [b for b in css.split("}") if "stElementToolbarButton" in b]
    assert toolbar, "no rule targets the dataframe toolbar buttons"
    joined = " ".join(toolbar).replace(" ", "")
    assert "min-height:44px" in joined and "min-width:44px" in joined


def test_the_ledger_is_neutral_by_row():
    """No full-row red/green, no per-row gradients, no heavy cell boxes."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    for block in css.split("}"):
        if "tl-ledger" in block and "tr" in block:
            assert "linear-gradient" not in block


def test_no_css_rule_named_tl_ledger_exists():
    """Why the test above proves nothing, stated rather than left implied.

    Its loop body never runs: there is no `tl-ledger` class anywhere in the
    product. The ledger is `st.dataframe` over a pandas Styler, so its row
    styling is decided in Python, not CSS, and no CSS scan can see it. Kept
    as a guard against someone reintroducing a CSS ledger and assuming this
    file already covers it.
    """
    from src.tradelens.ui import design_system as ds

    assert "tl-ledger" not in ds.build_css()


def test_the_demo_ledger_shows_labels_not_database_columns():
    """Measured in the browser at 1440: this table was the one surface still
    exposing `trade_date` / `setup_type` / `killzone` / `pnl`, both visually
    and through the data grid's ARIA table. It is the first ledger a trader
    with an empty journal ever sees, so it must read like the real one.
    """
    source = Path("src/tradelens/ui/pages/2_Trades.py").read_text()
    assert '"killzone": "Session"' in source
    assert '"pnl": "P&L"' in source
    # The raw names may still appear as rename KEYS, never as a bare column list.
    assert '"trade_date",\n' not in source


def test_the_journal_uses_no_emoji_as_an_icon():
    """The Journal's share of the emoji handed forward by the Task 2 amendment.

    `:material/...:` is used rather than a ligature string here because this is
    Streamlit's own `icon=` parameter, which resolves the shortcode. That is
    the opposite of the authored-HTML case, where Task 2 had to use ligature
    names because a shortcode would have been escaped and rendered literally.
    """
    source = Path("src/tradelens/ui/pages/2_Trades.py").read_text()
    found = re.findall(r"[✅\U0001F300-\U0001FAFF]", source)
    assert not found, f"2_Trades.py still passes emoji as an icon: {found}"
    assert 'icon=":material/' in source, "the toasts still need an icon"


def test_money_and_dates_use_tabular_numerals():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    assert "font-variant-numeric: tabular-nums" in css


def test_clear_filters_is_subordinate_to_the_primary_action():
    from tests.source_probe import near

    source = Path("src/tradelens/ui/pages/2_Trades.py").read_text()
    assert 'type="primary"' not in near(source, "Clear filters")

from __future__ import annotations

import datetime as dt
import re
from dataclasses import replace

import pytest

from scripts.capture_app_screenshots import (
    AUDIT_CAPTURES,
    CAPTURE_ANCHOR,
    MARKETING_CAPTURES,
    CaptureSpec,
    capture_mode,
    center_of_box,
    click_center,
    park_pointer,
    redact_url,
    validate_page_state,
)


EXPECTED_AUDIT = {
    "overview-desktop": ("/", 1440, 1000, False, False),
    "new-trade-desktop": ("/NewTrade", 1440, 1000, False, False),
    "journal-desktop": ("/Trades", 1440, 1000, False, False),
    "analytics-desktop": ("/Analytics", 1440, 1000, False, False),
    "ai-reviews-desktop": ("/Insights", 1440, 1000, False, False),
    "strategy-desktop": ("/Strategy", 1440, 1000, False, False),
    "settings-desktop": ("/Settings", 1440, 1000, False, False),
    "partner-drawer-desktop": ("/", 1440, 1000, False, True),
    "partner-page-phone": ("/Partner", 375, 812, True, False),
}

EXPECTED_MARKETING = {
    "overview": ("/", "site/assets/shot-dashboard-wide.webp", 1600, 1000),
    "new-trade": ("/NewTrade", "site/assets/shot-newtrade.webp", 1400, 933),
    "analytics": ("/Analytics", "site/assets/shot-analytics.webp", 1400, 933),
    "strategy": ("/Strategy", "site/assets/shot-strategy.webp", 1400, 933),
}


def test_audit_manifest_covers_every_destination_and_partner_presentation():
    actual = {
        capture.name: (
            capture.route,
            capture.width,
            capture.height,
            capture.coarse_pointer,
            capture.open_partner,
        )
        for capture in AUDIT_CAPTURES
    }
    assert actual == EXPECTED_AUDIT


def test_marketing_manifest_preserves_paths_routes_and_declared_geometry():
    actual = {
        capture.name: (
            capture.route,
            capture.output.as_posix(),
            capture.width,
            capture.height,
        )
        for capture in MARKETING_CAPTURES
    }
    assert actual == EXPECTED_MARKETING


def test_capture_manifests_have_unique_names_and_outputs():
    captures = (*MARKETING_CAPTURES, *AUDIT_CAPTURES)
    names = [capture.name for capture in captures]
    outputs = [capture.output for capture in captures]
    assert len(names) == len(set(names))
    assert len(outputs) == len(set(outputs))


def test_capture_artifacts_are_scoped_and_use_the_required_formats():
    assert CAPTURE_ANCHOR == dt.date(2026, 8, 9)
    for capture in MARKETING_CAPTURES:
        assert capture.output.parts[:2] == ("site", "assets")
        assert capture.output.suffix == ".webp"
    for capture in AUDIT_CAPTURES:
        assert capture.output.parts[:5] == (
            "docs",
            "superpowers",
            "audits",
            "assets",
            "2026-08-09",
        )
        assert capture.output.suffix == ".png"
    assert all(
        not capture.output.is_absolute() and ".." not in capture.output.parts
        for capture in (*MARKETING_CAPTURES, *AUDIT_CAPTURES)
    )


def test_redact_url_removes_auth_and_any_other_query_values():
    safe = redact_url(
        "http://localhost:8599/Insights?auth=secret.session.token&tab=weekly#note"
    )
    assert safe == "http://localhost:8599/Insights?auth=REDACTED&tab=REDACTED#note"
    assert "secret.session.token" not in safe
    assert "weekly" not in safe


def _good_state(*, coarse: bool = False) -> dict[str, object]:
    return {
        "overflow": 0,
        "exceptionCount": 0,
        "coarse": coarse,
        "reduced": True,
        "scrollTop": 0,
        "frameworkChromeCount": 0,
        "text": "Aug 8, 2026\nICT/SMC Day Trading\nPost-trade review",
        "url": "http://localhost:8599/?auth=secret.session.token",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"overflow": 1}, "horizontal overflow"),
        ({"exceptionCount": 1}, "rendered 1 exception"),
        ({"coarse": True}, "pointer state"),
        ({"reduced": False}, "reduced-motion"),
        ({"scrollTop": 32}, "scrolled away from the top"),
        ({"frameworkChromeCount": 1}, "framework chrome"),
        ({"text": "Sign in to use the AI Partner"}, "signed-out Partner"),
        ({"text": "2026-08-10"}, "later than capture anchor"),
        ({"text": "2026/08/10"}, "later than capture anchor"),
        ({"text": "August 10, 2026"}, "later than capture anchor"),
        ({"text": "Aug 10–16, 2026"}, "later than capture anchor"),
        ({"text": "secret.session.token"}, "session credential"),
    ],
)
def test_page_state_validation_rejects_every_capture_contaminant(mutation, message):
    spec = AUDIT_CAPTURES[0]
    state = {**_good_state(), **mutation}
    with pytest.raises(RuntimeError, match=message):
        validate_page_state(spec, state, auth_token="secret.session.token")


def test_page_state_validation_accepts_the_exact_anchor_and_phone_pointer():
    desktop = AUDIT_CAPTURES[0]
    validate_page_state(
        desktop,
        {**_good_state(), "text": "August 9, 2026\n2026-08-09"},
        auth_token="secret.session.token",
    )

    phone = next(c for c in AUDIT_CAPTURES if c.name == "partner-page-phone")
    validate_page_state(
        phone,
        _good_state(coarse=True),
        auth_token="secret.session.token",
    )


def test_partner_pointer_target_uses_the_quadrilateral_center():
    assert center_of_box((10, 20, 110, 20, 110, 80, 10, 80)) == (60, 50)


def test_partner_pointer_action_uses_a_complete_trusted_mouse_sequence():
    from tornado.ioloop import IOLoop

    class RecordingTab:
        def __init__(self):
            self.events = []

        async def box_model(self, selector):
            assert selector == ".partner-launcher"
            return (10, 20, 110, 20, 110, 80, 10, 80)

        async def mouse(self, event_type, **params):
            self.events.append((event_type, params))

    tab = RecordingTab()
    IOLoop.current().run_sync(lambda: click_center(tab, ".partner-launcher"))
    assert tab.events == [
        ("mouseMoved", {"x": 60, "y": 50}),
        (
            "mousePressed",
            {"x": 60, "y": 50, "button": "left", "click_count": 1},
        ),
        (
            "mouseReleased",
            {"x": 60, "y": 50, "button": "left", "click_count": 1},
        ),
    ]


def test_pointer_is_parked_outside_the_viewport_before_the_shutter():
    from tornado.ioloop import IOLoop

    class RecordingTab:
        def __init__(self):
            self.events = []

        async def mouse(self, event_type, **params):
            self.events.append((event_type, params))

    tab = RecordingTab()
    IOLoop.current().run_sync(lambda: park_pointer(tab))
    assert tab.events == [("mouseMoved", {"x": -100, "y": -100})]


def test_capture_modes_are_mutually_exclusive_and_intentional():
    assert capture_mode(["--marketing"]) == "marketing"
    assert capture_mode(["--audit"]) == "audit"
    assert capture_mode(["--all"]) == "all"
    with pytest.raises(ValueError, match="choose exactly one"):
        capture_mode([])
    with pytest.raises(ValueError, match="choose exactly one"):
        capture_mode(["--audit", "--marketing"])


def test_capture_spec_is_frozen():
    capture = MARKETING_CAPTURES[0]
    with pytest.raises(Exception):
        capture.width = 1
    assert replace(capture, width=1) == CaptureSpec(
        name=capture.name,
        route=capture.route,
        output=capture.output,
        width=1,
        height=capture.height,
        coarse_pointer=capture.coarse_pointer,
        open_partner=capture.open_partner,
    )


def test_phone_product_nav_replaces_streamlits_sidebar_expander():
    from src.tradelens.ui.design_system import build_css

    css = build_css()
    selector = '[data-testid="stExpandSidebarButton"]'
    phone = css.rindex("@media (max-width: 767px)")
    hidden_rules = [
        match.start()
        for match in re.finditer(re.escape(selector) + r"[^{}]*\{([^{}]*)\}", css)
        if "display: none" in match.group(1)
    ]
    assert hidden_rules and min(hidden_rules) > phone

    mobile_nav = css[css.index(".tl-mobile-nav", phone) :]
    assert "display: flex" in mobile_nav[: mobile_nav.index("}")]

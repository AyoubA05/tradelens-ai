"""`GET /v1/analytics` — one owner, one period, one filtered sample.

Financial correctness is the boundary here. A wrong number on this page is a
false claim about a trader's money that they have no way to detect, so the
tests below care less about shape than about whether a figure could ever be
fabricated, widened, or drawn from someone else's rows.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from src.tradelens.services import trade_service

SECRET = "test-service-secret-value-at-least-32-bytes"
PATH = "/v1/analytics"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.invalid/tradelens?sslmode=require",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(handle: str, query: str) -> dict:
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", PATH, query, b"")
    return {
        "X-TL-Signature": "v1={}:{}".format(ts, sig),
        "X-TL-Session-Handle": handle,
    }


def _get(client, handle, query: str):
    return client.get("{}?{}".format(PATH, query), headers=_headers(handle, query))


def _seed(user_id: int, **over):
    data = {
        "asset": "NQ",
        "trade_date": "2026-09-10",
        "result": "Win",
        "pnl": 250.0,
        "session": "New York",
        "setup_type": "FVG",
        "strategy_used": "ICT",
    }
    data.update(over)
    return trade_service.create_trade(data, user_id=user_id)


SEPT = "from=2026-09-01&to=2026-09-30"


def _session_handle_for(user_id: int) -> str:
    """A live website session handle for an ARBITRARY user.

    `website_session_handle` always authenticates `two_users[0]`, which is
    user id 1 in a fresh database. That makes it blind to an endpoint that
    hardcodes `user_id=1`: the wrong owner and the right owner are the same
    row, so every isolation assertion passes against code that ignores the
    session entirely. Authenticating the SECOND user is what separates them.
    """
    import datetime as dt
    import hashlib
    import secrets

    from sqlalchemy import text as sa_text

    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services import auth_sessions

    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_id,
                "c": now,
                "e": now + dt.timedelta(hours=12),
                "l": now,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    return digest


# ------------------------------------------------------------- isolation


def test_the_analytics_belong_to_the_AUTHENTICATED_owner_not_the_first_user(
    client, two_users
):
    """Authenticates the SECOND user, deliberately.

    Every other isolation test here authenticates `two_users[0]` — user 1 in
    a fresh database — so an endpoint that hardcoded `user_id=1` would pass
    all of them while ignoring the session completely. This is the only test
    in the file where "the authenticated owner" and "the first user" are
    different rows, which is what makes it able to fail.
    """
    first, second = two_users[0], two_users[1]
    _seed(first, pnl=111.0)
    _seed(second, pnl=222.0, trade_date="2026-09-11")
    handle = _session_handle_for(second)

    body = _get(client, handle, SEPT).json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(222.0)


def test_another_owner_s_trades_never_appear_in_this_owner_s_analytics(
    client, website_session_handle, two_users
):
    """Tenant isolation on an aggregate fails invisibly.

    A leaked row does not look foreign — the number is merely larger. There
    is no per-row identity on this page for a trader to check against.
    """
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    _seed(owner, pnl=100.0)
    _seed(other, pnl=9999.0, trade_date="2026-09-11")

    body = _get(client, handle, SEPT).json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)


def test_every_breakdown_is_owner_scoped_too_not_just_the_headline(
    client, website_session_handle, two_users
):
    """The headline could be right while a breakdown leaks.

    They are built from one frame, but that is an implementation fact — this
    pins it as a guarantee, so a future refactor that re-queries inside a
    breakdown cannot quietly widen it.
    """
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    _seed(owner, asset="NQ")
    _seed(other, asset="GOLD", trade_date="2026-09-12")

    body = _get(client, handle, SEPT).json()
    assets = [row["key"] for row in body["setups"]["by_asset"]["rows"]]

    assert assets == ["NQ"]


# ------------------------------------------------------- date boundaries


@pytest.mark.parametrize(
    "trade_date,included",
    [
        ("2026-08-31", False),
        ("2026-09-01", True),
        ("2026-09-30", True),
        ("2026-10-01", False),
    ],
)
def test_the_period_is_inclusive_at_both_ends_and_excludes_neighbours(
    client, website_session_handle, trade_date, included
):
    """Off-by-one at a period edge moves money between months silently."""
    owner, handle = website_session_handle
    _seed(owner, trade_date=trade_date, pnl=100.0)

    body = _get(client, handle, SEPT).json()

    assert body["performance"]["total_trades"] == (1 if included else 0)


def test_a_malformed_period_is_refused_rather_than_guessed(
    client, website_session_handle
):
    """A range nothing can render is worse than a refusal.

    Silently widening or narrowing it would answer a question the trader did
    not ask, with numbers they would have no reason to doubt.
    """
    _owner, handle = website_session_handle
    assert _get(client, handle, "from=2026-9-1&to=2026-09-30").status_code == 422
    assert _get(client, handle, "from=20260901&to=2026-09-30").status_code == 422
    assert _get(client, handle, "from=2026-09-01&to=not-a-date").status_code == 422


def test_an_inverted_period_is_refused(client, website_session_handle):
    _owner, handle = website_session_handle
    assert _get(client, handle, "from=2026-09-30&to=2026-09-01").status_code == 422


def test_the_largest_iso_date_does_not_crash_the_window_validator(
    client, website_session_handle
):
    _owner, handle = website_session_handle

    response = _get(client, handle, "from=9999-12-31&to=9999-12-31")

    assert response.status_code == 200
    assert response.json()["period"] == {"from": "9999-12-31", "to": "9999-12-31"}


def test_a_period_with_no_possible_prior_window_is_a_422_not_a_500(
    client, website_session_handle
):
    _owner, handle = website_session_handle

    response = _get(client, handle, "from=0001-01-01&to=0001-01-01")

    assert response.status_code == 422
    assert response.json()["detail"] == "period has no preceding comparison window"


def test_the_response_echoes_the_period_it_actually_used(
    client, website_session_handle
):
    """So a reader can tell the window was honoured, not adjusted."""
    _owner, handle = website_session_handle
    body = _get(client, handle, SEPT).json()
    assert body["period"] == {"from": "2026-09-01", "to": "2026-09-30"}


# ------------------------------------------------------------- filtering


def test_a_filter_narrows_the_sample_server_side(client, website_session_handle):
    """A filter applied only in the browser shows a total over rows the
    trader cannot see on the page."""
    owner, handle = website_session_handle
    _seed(owner, asset="NQ", pnl=100.0)
    _seed(owner, asset="ES", pnl=500.0, trade_date="2026-09-11")

    body = _get(client, handle, SEPT + "&asset=NQ").json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)
    assert body["filters"] == {"asset": "NQ"}


def test_an_asset_filter_is_exact_and_does_not_swallow_a_similar_symbol(
    client, website_session_handle
):
    """`NQ` must not match `MNQ`.

    Phase 3 shipped this bug on the trades list and fixed it with an exact
    comparison. `get_trades` still uses `ilike('%..%')`, so reusing its
    filters here would fold MNQ into an NQ trader's TOTAL — the one place
    the error is invisible, because there are no rows on screen to count.
    """
    owner, handle = website_session_handle
    _seed(owner, asset="NQ", pnl=100.0)
    _seed(owner, asset="MNQ", pnl=700.0, trade_date="2026-09-11")

    body = _get(client, handle, SEPT + "&asset=NQ").json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)


def test_the_strategy_filter_narrows_the_sample(client, website_session_handle):
    """The wire name and the column name deliberately differ.

    `strategy` on the query string maps to the `strategy_used` column, so the
    browser is not writing schema into a URL. That mapping is the whole job
    of the filter allowlist — and it is invisible to the asset and session
    filters, whose wire names happen to equal their column names. Without
    this test, replacing the allowlist with a passthrough silently disables
    the strategy filter and every other test still passes.
    """
    owner, handle = website_session_handle
    _seed(owner, strategy_used="ICT", pnl=100.0)
    _seed(owner, strategy_used="Breakout", pnl=900.0, trade_date="2026-09-11")

    body = _get(client, handle, SEPT + "&strategy=ICT").json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)
    assert body["filters"] == {"strategy": "ICT"}


def test_a_session_filter_narrows_the_sample(client, website_session_handle):
    owner, handle = website_session_handle
    _seed(owner, session="New York", pnl=100.0)
    _seed(owner, session="London", pnl=900.0, trade_date="2026-09-11")

    body = _get(client, handle, SEPT + "&session=New York").json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)


def test_a_filter_that_matches_nothing_reports_no_sample_not_zero(
    client, website_session_handle
):
    owner, handle = website_session_handle
    _seed(owner, asset="NQ", pnl=100.0)

    body = _get(client, handle, SEPT + "&asset=GOLD").json()

    assert body["performance"]["total_trades"] == 0
    assert body["performance"]["total_pnl"]["value"] is None
    assert body["performance"]["total_pnl"]["state"] is not None


# ------------------------------------------- undefined vs measured zero


def test_a_zero_trade_range_reports_undefined_everywhere_not_zeroes(
    client, website_session_handle
):
    """Not one plausible zero anywhere on an empty page."""
    owner, handle = website_session_handle
    _seed(owner, trade_date="2026-01-05")

    body = _get(client, handle, SEPT).json()

    perf = body["performance"]
    assert perf["total_trades"] == 0
    for field in ("total_pnl", "win_rate", "expectancy", "profit_factor"):
        assert perf[field]["value"] is None, field
        assert perf[field]["state"] is not None, field


def test_a_sample_with_some_missing_pnl_reports_no_total(
    client, website_session_handle
):
    """A journal kept for the process has not earned a total of $0.00."""
    owner, handle = website_session_handle
    _seed(owner, pnl=250.0)
    _seed(owner, pnl=None, result="Loss", trade_date="2026-09-11")

    body = _get(client, handle, SEPT).json()

    assert body["performance"]["total_pnl"]["state"] == "undefined_incomplete_sample"


def test_a_win_rate_survives_a_sample_with_no_pnl_at_all(
    client, website_session_handle
):
    """Win rate and P&L are INDEPENDENTLY SOURCED.

    `win_rate` comes from `result`; `total_pnl` comes from `pnl`. A trader
    who labels outcomes without recording amounts has a perfectly valid win
    rate, and the API must keep saying so — Group C is required not to imply
    one validates the other.
    """
    owner, handle = website_session_handle
    _seed(owner, pnl=None, result="Win")
    _seed(owner, pnl=None, result="Loss", trade_date="2026-09-11")

    body = _get(client, handle, SEPT).json()

    assert body["performance"]["win_rate"]["value"] == pytest.approx(0.5)
    assert body["performance"]["win_rate"]["state"] is None
    assert body["performance"]["total_pnl"]["value"] is None


def test_a_genuinely_breakeven_period_reports_a_measured_zero(
    client, website_session_handle
):
    """The other direction. Over-gating erases a real result."""
    owner, handle = website_session_handle
    _seed(owner, pnl=100.0, result="Win")
    _seed(owner, pnl=-100.0, result="Loss", trade_date="2026-09-11")

    body = _get(client, handle, SEPT).json()

    assert body["performance"]["total_pnl"] == {"value": 0.0, "state": None}


def test_a_single_trade_range_refuses_a_drawdown_it_cannot_measure(
    client, website_session_handle
):
    owner, handle = website_session_handle
    _seed(owner, pnl=250.0)

    body = _get(client, handle, SEPT).json()

    assert body["risk"]["max_drawdown"]["state"] == "undefined_no_sample"


# --------------------------------------------- one sample, one set of rows


def test_the_headline_count_and_every_breakdown_describe_the_same_sample(
    client, website_session_handle
):
    """Totals and breakdowns must come from the SAME filtered set.

    Counting rows rather than summing money on purpose: this is an integrity
    check on the wire, not a second computation of a figure. If a breakdown
    were built from an unfiltered or re-queried frame, its trade counts
    would no longer add up to the headline.
    """
    owner, handle = website_session_handle
    _seed(owner, asset="NQ", session="New York", pnl=100.0)
    _seed(
        owner,
        asset="ES",
        session="London",
        pnl=-50.0,
        result="Loss",
        trade_date="2026-09-11",
    )
    _seed(owner, asset="NQ", session="London", pnl=25.0, trade_date="2026-09-12")

    body = _get(client, handle, SEPT + "&asset=NQ").json()
    total = body["performance"]["total_trades"]

    assert total == 2
    for lens, key in (
        ("setups", "by_asset"),
        ("setups", "by_setup"),
        ("timing", "by_session"),
        ("timing", "by_day_of_week"),
    ):
        rows = body[lens][key]["rows"]
        assert sum(row["trades"] for row in rows) == total, "{}.{}".format(lens, key)


# ----------------------------------------------------------- odd labels


def test_a_strange_category_label_survives_the_wire_intact(
    client, website_session_handle
):
    """Category keys are trader-typed and reach the browser as text.

    They must arrive unmangled — neither escaped twice nor truncated — so
    the page can render them safely and the trader recognises their own
    label.
    """
    owner, handle = website_session_handle
    odd = "Odd/Name & <x> 'quoted'"
    _seed(owner, setup_type=odd, pnl=100.0)

    body = _get(client, handle, SEPT).json()
    keys = [row["key"] for row in body["setups"]["by_setup"]["rows"]]

    assert keys == [odd]


def test_a_single_category_is_not_reported_as_comparable(
    client, website_session_handle
):
    """One category is not a ranking, and the API decides that, not the UI."""
    owner, handle = website_session_handle
    _seed(owner, setup_type="FVG", pnl=100.0)

    body = _get(client, handle, SEPT).json()

    assert body["setups"]["by_setup"]["comparable"] is False


# --------------------------------------------------------- contract drift


def test_every_numeric_headline_is_a_value_state_pair_not_a_bare_number(
    client, website_session_handle
):
    """A bare float has nowhere to put "not measurable", so it eventually
    puts a zero there."""
    owner, handle = website_session_handle
    _seed(owner)

    body = _get(client, handle, SEPT).json()

    for lens, fields in (
        ("performance", ("total_pnl", "win_rate", "expectancy", "profit_factor")),
        ("risk", ("max_drawdown", "avg_win", "avg_loss")),
        ("discipline", ("rule_adherence", "consistency", "edge_leak")),
    ):
        for field in fields:
            assert set(body[lens][field]) == {"value", "state"}, "{}.{}".format(
                lens, field
            )


def test_the_response_carries_no_hour_of_day_breakdown(client, website_session_handle):
    """No clock component is persisted, so the panel was removed rather than
    shipped permanently empty (see the plan's Scope)."""
    owner, handle = website_session_handle
    _seed(owner)

    assert "by_hour" not in _get(client, handle, SEPT).json()["timing"]


def test_an_unknown_query_parameter_is_refused_rather_than_ignored(
    client, website_session_handle
):
    """A silently-ignored filter shows a total the trader thinks is narrowed."""
    owner, handle = website_session_handle
    _seed(owner)

    response = _get(client, handle, SEPT + "&setup=FVG")

    assert response.status_code == 422


# ----------------------------------------------- contract invariants


def test_a_metric_value_cannot_carry_both_a_number_and_an_undefined_state():
    """The contract enforces the rule, not just the service's discipline.

    Without this the type only DESCRIBES undefined-never-zero while the
    projection is the sole thing upholding it — and the contract layer is
    exactly where service drift is supposed to be caught. A 0.0 riding
    alongside `undefined_incomplete_sample` would otherwise serialise
    straight onto a trader's screen.
    """
    from pydantic import ValidationError

    from src.tradelens.api.schemas.analytics import MetricValue

    MetricValue(value=1.0, state=None)
    MetricValue(value=None, state="undefined_no_sample")

    with pytest.raises(ValidationError):
        MetricValue(value=1.0, state="undefined_nan")
    with pytest.raises(ValidationError):
        MetricValue(value=None, state=None)


def test_the_full_response_contract_refuses_extra_missing_and_wrongly_typed_fields(
    client, website_session_handle
):
    """Strictness must protect the actual nested payload, not only MetricValue."""
    from copy import deepcopy

    from pydantic import ValidationError

    from src.tradelens.api.schemas.analytics import AnalyticsResponse

    owner, handle = website_session_handle
    _seed(owner)
    valid = _get(client, handle, SEPT).json()
    AnalyticsResponse.model_validate(valid)

    extra = deepcopy(valid)
    extra["performance"]["plausible_new_metric"] = {
        "value": 0.0,
        "state": None,
    }
    with pytest.raises(ValidationError):
        AnalyticsResponse.model_validate(extra)

    missing = deepcopy(valid)
    del missing["risk"]["max_drawdown"]
    with pytest.raises(ValidationError):
        AnalyticsResponse.model_validate(missing)

    wrong_type = deepcopy(valid)
    wrong_type["performance"]["total_trades"] = "1"
    with pytest.raises(ValidationError):
        AnalyticsResponse.model_validate(wrong_type)


def test_a_multi_category_breakdown_is_reported_as_comparable(
    client, website_session_handle
):
    """The TRUE direction of `comparable`, which nothing else pinned.

    Only the False side was tested, so a flag stuck at False passed the whole
    suite — and Group C's ranking language rests entirely on this flag, so
    stuck-False would silently suppress ranking product-wide with nothing
    failing anywhere.
    """
    owner, handle = website_session_handle
    _seed(owner, setup_type="FVG", pnl=100.0)
    _seed(owner, setup_type="OB", pnl=-50.0, result="Loss", trade_date="2026-09-11")

    body = _get(client, handle, SEPT).json()

    assert body["setups"]["by_setup"]["comparable"] is True
    assert len(body["setups"]["by_setup"]["rows"]) == 2


def test_a_permissive_fromisoformat_still_cannot_widen_the_period(
    client, website_session_handle, monkeypatch
):
    """The regex pre-check must bite on BOTH runtimes.

    Python 3.9 (the local floor) already rejects `20260901`,
    `2026-09-01T00:00:00` and `2026-9-1`, so deleting the regex guard reads
    green here while CI's 3.11 — which accepts all three — would silently
    widen the window. Stubbing a permissive parser makes the guard's absence
    visible on the floor runtime too.
    """
    import datetime as real_dt

    from src.tradelens.api.routers import overview as overview_router

    class _Permissive(real_dt.date):
        @classmethod
        def fromisoformat(cls, value):
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return real_dt.datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            return real_dt.datetime.strptime(value.replace("-", "-"), "%Y-%m-%d").date()

    monkeypatch.setattr(overview_router.dt, "date", _Permissive)
    _owner, handle = website_session_handle

    assert _get(client, handle, "from=20260901&to=2026-09-30").status_code == 422
    assert (
        _get(client, handle, "from=2026-09-01T00:00:00&to=2026-09-30").status_code
        == 422
    )


# ------------------------------------------------- the prior-period comparison


def test_the_prior_period_is_derived_and_reported_with_its_real_dates(
    client, website_session_handle
):
    """Derived, never selected — that is what keeps ONE date control.

    A "compare to" picker would be a second window on one screen, and a
    reader could not tell which number belonged to which. The response
    states the dates it actually used so the comparison is legible without
    one.
    """
    owner, handle = website_session_handle
    _seed(owner, trade_date="2026-09-10", pnl=100.0)
    _seed(owner, trade_date="2026-08-20", pnl=40.0)

    body = _get(client, handle, SEPT).json()

    # September has 30 days, so the prior window is the 30 days before it.
    assert body["comparison"]["period"] == {"from": "2026-08-02", "to": "2026-08-31"}
    assert body["comparison"]["net_pnl"]["value"] == pytest.approx(60.0)


def test_a_comparison_with_no_prior_trades_is_undefined_not_zero(
    client, website_session_handle
):
    """ "No prior period to compare against" is not "no change"."""
    owner, handle = website_session_handle
    _seed(owner, trade_date="2026-09-10", pnl=100.0)

    body = _get(client, handle, SEPT).json()

    assert body["comparison"]["net_pnl"]["value"] is None
    assert body["comparison"]["net_pnl"]["state"] == "undefined_no_sample"


def test_the_comparison_uses_the_same_filters_as_the_period_itself(
    client, website_session_handle
):
    """Otherwise the delta compares NQ against everything and calls it change."""
    owner, handle = website_session_handle
    _seed(owner, trade_date="2026-09-10", asset="NQ", pnl=100.0)
    _seed(owner, trade_date="2026-08-20", asset="NQ", pnl=40.0)
    _seed(owner, trade_date="2026-08-21", asset="ES", pnl=5000.0)

    body = _get(client, handle, SEPT + "&asset=NQ").json()

    assert body["comparison"]["net_pnl"]["value"] == pytest.approx(60.0)


def test_the_comparison_is_owner_scoped_like_everything_else(client, two_users):
    first, second = two_users[0], two_users[1]
    _seed(first, trade_date="2026-08-20", pnl=9999.0)
    _seed(second, trade_date="2026-09-10", pnl=100.0)
    _seed(second, trade_date="2026-08-20", pnl=40.0)
    handle = _session_handle_for(second)

    body = _get(client, handle, SEPT).json()

    assert body["comparison"]["net_pnl"]["value"] == pytest.approx(60.0)

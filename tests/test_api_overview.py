# tests/test_api_overview.py
"""The Overview endpoint.

The security properties are the point: the owner comes from the session row,
the period is validated server-side even though the HMAC already covers it,
and a second trader's data is unreachable.
"""
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from tests.parity.dataset import seed_golden_dataset

SECRET = "test-service-secret-value-at-least-32-bytes"
PATH = "/v1/overview"
QUERY = "from=2026-08-01&to=2026-08-31"


@pytest.fixture
def client(monkeypatch):
    # Mirrors tests/test_api_security.py's `client` fixture: `validate_api_runtime`
    # requires a >=32 byte secret and a postgres-looking DATABASE_URL at app
    # creation time. The `two_users` fixture (pulled in transitively via
    # `website_session_handle`) later overwrites DATABASE_URL to the isolated
    # sqlite tmp path and patches `settings.database_url` directly — that is
    # what the service layer actually reads, so this fake postgres URL only
    # needs to satisfy the one-time production-config check, never a real query.
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.invalid/tradelens?sslmode=require",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(handle, *, query=QUERY, path=PATH):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", path, query, b"")
    return {"X-TL-Signature": f"v1={ts}:{sig}", "X-TL-Session-Handle": handle}


def test_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    assert (
        client.get(
            f"{PATH}?{QUERY}", headers={"X-TL-Session-Handle": handle}
        ).status_code
        == 401
    )


def test_request_without_a_session_is_refused(client):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", PATH, QUERY, b"")
    r = client.get(f"{PATH}?{QUERY}", headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_returns_the_owner_s_overview(client, website_session_handle):
    user_id, handle = website_session_handle
    seed_golden_dataset(user_id)
    r = client.get(f"{PATH}?{QUERY}", headers=_headers(handle))
    assert r.status_code == 200
    body = r.json()
    assert body["kpi"]["net_pnl"] == {"value": 575.0, "state": None}
    assert body["kpi"]["trades"] == 5


def test_never_returns_another_owner_s_data(client, website_session_handle, two_users):
    """A signed, authenticated request still only sees its own rows."""
    user_id, handle = website_session_handle
    other = [u for u in two_users if u != user_id][0]
    seed_golden_dataset(other)

    # Positive control: prove the golden dataset actually landed on the other
    # owner before asserting the requesting owner can't see it. Without this,
    # a future regression that made `seed_golden_dataset` a no-op would leave
    # both assertions trivially true and this test green for the wrong reason
    # — on the endpoint that guards tenant isolation, the cardinal property.
    from src.tradelens.services.overview import build_overview

    other_data = build_overview(user_id=other, start="2026-08-01", end="2026-08-31")
    assert other_data["kpi"]["trades"] == 5

    body = client.get(f"{PATH}?{QUERY}", headers=_headers(handle)).json()
    assert body["kpi"]["trades"] == 0


def test_browser_supplied_owner_aliases_cannot_change_the_tenant(
    client, website_session_handle, two_users
):
    """Exercise the actual signed request, not merely a service call.

    Common owner aliases are included as independently signed query input. If
    a future handler begins threading any of them into the service, this test
    exposes the other tenant's seeded data instead of passing vacuously.
    """
    user_id, handle = website_session_handle
    other = next(candidate for candidate in two_users if candidate != user_id)
    seed_golden_dataset(other)
    query = (
        f"{QUERY}&user_id={other}&uid={other}&owner={other}"
        f"&accountId={other}&account_id={other}"
    )

    response = client.get(f"{PATH}?{query}", headers=_headers(handle, query=query))
    assert response.status_code == 200
    assert response.json()["kpi"]["trades"] == 0


def test_a_tampered_period_fails_the_signature(client, website_session_handle):
    """The query is bound into the HMAC, so the range cannot be edited in transit."""
    _, handle = website_session_handle
    r = client.get(f"{PATH}?from=1990-01-01&to=2099-01-01", headers=_headers(handle))
    assert r.status_code == 401


def test_a_nonsense_period_is_rejected_with_422(client, website_session_handle):
    """Authenticated is not the same as valid."""
    _, handle = website_session_handle
    bad = "from=not-a-date&to=2026-08-31"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_a_reversed_period_is_rejected(client, website_session_handle):
    _, handle = website_session_handle
    bad = "from=2026-08-31&to=2026-08-01"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_a_span_over_five_years_is_rejected(client, website_session_handle):
    """A journal's analysis range has no legitimate reason to exceed five years."""
    _, handle = website_session_handle
    bad = "from=2015-01-01&to=2026-08-31"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422
    assert "5 years" in r.json()["detail"]


def test_a_runtime_lenient_date_form_is_still_rejected(client, website_session_handle):
    """`date.fromisoformat` alone accepts more on 3.11 than on 3.9.

    "20260201" parses under Python 3.11 (CI, the container) but not 3.9 (the
    local floor); without the regex pre-check the two runtimes would disagree
    about what returns 422 for the exact same request.
    """
    _, handle = website_session_handle
    bad = "from=20260201&to=2026-08-31"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_the_response_is_not_cacheable(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(f"{PATH}?{QUERY}", headers=_headers(handle))
    assert "no-store" in r.headers.get("cache-control", "")


def test_the_period_s_wire_field_is_from_not_from_(client, website_session_handle):
    """The request parameter is `from`; the response must echo that name, not
    the Python-safe `from_` the model uses internally."""
    _, handle = website_session_handle
    body = client.get(f"{PATH}?{QUERY}", headers=_headers(handle)).json()
    assert body["period"]["from"] == "2026-08-01"
    assert "from_" not in body["period"]


def test_the_schema_is_typed_not_a_bare_dict():
    """A dict response generates {[k:string]: unknown} and the drift gate then
    protects nothing.

    Checked end to end via the generated OpenAPI schema, which proves FastAPI
    actually wired `OverviewResponse` in as the response model — one step
    further than asserting the handler's return annotation, which could be
    correct while FastAPI still serialized through something else.
    """
    spec = create_app().openapi()
    ref = spec["paths"]["/v1/overview"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert ref.endswith("/OverviewResponse")


def test_an_unexpected_field_is_rejected_not_silently_dropped():
    """`extra="forbid"` is what makes the drift gate mean something: a
    `build_overview` field this contract doesn't know about must fail loudly,
    not vanish from the response while `openapi.json` stays unchanged."""
    from pydantic import ValidationError

    from src.tradelens.api.schemas.overview import Undefinable

    with pytest.raises(ValidationError):
        Undefinable(value=1.0, state=None, unexpected="surprise")


def test_a_missing_required_subobject_raises_not_nulls():
    """A service key renamed or removed underneath this contract must fail
    validation, not quietly validate as an all-null `{value: null, state:
    null}` figure with no state string to explain why it vanished."""
    from pydantic import ValidationError

    from src.tradelens.api.schemas.overview import Undefinable

    with pytest.raises(ValidationError):
        Undefinable(value=1.0)  # "state" omitted entirely


@pytest.mark.parametrize(
    ("model_name", "payload"),
    [
        ("Kpi", {"expectancy": "<missing>"}),
        ("RuleAdherence", {"rate": "<missing>"}),
        ("Trajectory", {"streak_type": "<missing>"}),
        ("NextReviewAction", {"next_key": "<missing>"}),
        ("RecentTrade", {"pnl": "<missing>"}),
    ],
)
def test_nullable_contract_fields_are_still_required(model_name, payload):
    """Nullable means an explicit JSON null, not an optional wire property."""
    from pydantic import ValidationError

    from src.tradelens.api.schemas import overview as schemas

    valid = {
        "Kpi": {
            "net_pnl": {"value": 0.0, "state": None},
            "win_rate": {"value": None, "state": "undefined_no_sample"},
            "expectancy": None,
            "expectancy_state": "undefined_no_sample",
            "profit_factor": None,
            "profit_factor_state": "undefined_no_sample",
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "today_pnl": {"value": 0.0, "state": None},
            "week_pnl": {"value": 0.0, "state": None},
        },
        "RuleAdherence": {"rate": None, "followed": 0, "recorded": 0},
        "Trajectory": {
            "equity_curve": [],
            "current_streak": 0,
            "streak_type": "none",
            "best_streak": 0,
            "worst_streak": 0,
            "average_win": {"value": None, "state": "undefined_no_sample"},
            "average_loss": {"value": None, "state": "undefined_no_sample"},
        },
        "NextReviewAction": {
            "completed": 0,
            "total": 3,
            "next_key": None,
            "is_activated": False,
            "trades_until_review": 5,
        },
        "RecentTrade": {
            "id": 1,
            "trade_date": None,
            "asset": None,
            "session": None,
            "setup_type": None,
            "result": None,
            "pnl": None,
            "rr_realized": None,
        },
    }[model_name]
    field = next(key for key, value in payload.items() if value == "<missing>")
    valid.pop(field)

    with pytest.raises(ValidationError):
        getattr(schemas, model_name).model_validate(valid)


@pytest.mark.parametrize(
    ("factory", "payload"),
    [
        ("CalendarDay", {"date": "2026-08-01", "pnl": 1.0, "outcome": "banana"}),
        (
            "Trajectory",
            {
                "equity_curve": [],
                "current_streak": 1,
                "streak_type": "banana",
                "best_streak": 1,
                "worst_streak": 0,
                "average_win": {"value": 1.0, "state": None},
                "average_loss": {"value": None, "state": "undefined_no_sample"},
            },
        ),
        (
            "RecentTrade",
            {
                "id": 1,
                "trade_date": None,
                "asset": None,
                "session": None,
                "setup_type": None,
                "result": "Maybe",
                "pnl": None,
                "rr_realized": None,
            },
        ),
    ],
)
def test_enum_like_response_fields_reject_unknown_values(factory, payload):
    from pydantic import ValidationError

    from src.tradelens.api.schemas import overview as schemas

    with pytest.raises(ValidationError):
        getattr(schemas, factory).model_validate(payload)


def test_undefinable_requires_exactly_one_of_value_or_state():
    from pydantic import ValidationError

    from src.tradelens.api.schemas.overview import Undefinable

    with pytest.raises(ValidationError):
        Undefinable(value=None, state=None)
    with pytest.raises(ValidationError):
        Undefinable(value=1.0, state="undefined_no_sample")


def test_response_models_do_not_coerce_wrong_scalar_types():
    from pydantic import ValidationError

    from src.tradelens.api.schemas.overview import CalendarDay

    with pytest.raises(ValidationError):
        CalendarDay(date="2026-08-01", pnl="1.25", outcome="positive")


def test_trajectory_fields_that_the_service_always_emits_are_not_nullable():
    from pydantic import ValidationError

    from src.tradelens.api.schemas.overview import Trajectory

    with pytest.raises(ValidationError):
        Trajectory(
            equity_curve=[],
            current_streak=None,
            streak_type="none",
            best_streak=0,
            worst_streak=0,
            average_win={"value": None, "state": "undefined_no_sample"},
            average_loss={"value": None, "state": "undefined_no_sample"},
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "2026-08-01", "pnl": None, "outcome": "flat"},
        {"date": "2026-08-01", "pnl": 0.0, "outcome": "unknown"},
        {"date": "2026-08-01", "pnl": -1.0, "outcome": "positive"},
        {"date": "2026-08-01", "pnl": 1.0, "outcome": "flat"},
    ],
)
def test_calendar_outcome_and_pnl_cannot_contradict_each_other(payload):
    from pydantic import ValidationError

    from src.tradelens.api.schemas.overview import CalendarDay

    with pytest.raises(ValidationError):
        CalendarDay.model_validate(payload)


def test_openapi_marks_nullable_fields_required_and_keeps_unions_narrow():
    schemas = create_app().openapi()["components"]["schemas"]
    assert "expectancy" in schemas["Kpi"]["required"]
    assert "streak_type" in schemas["Trajectory"]["required"]
    assert "next_key" in schemas["NextReviewAction"]["required"]
    assert "pnl" in schemas["RecentTrade"]["required"]
    assert schemas["CalendarDay"]["properties"]["outcome"]["enum"] == [
        "positive",
        "negative",
        "flat",
        "unknown",
    ]

    next_key = schemas["NextReviewAction"]["properties"]["next_key"]
    member = next(part for part in next_key["anyOf"] if "enum" in part)
    assert member["enum"] == ["strategy", "first_trade", "weekly_review"]

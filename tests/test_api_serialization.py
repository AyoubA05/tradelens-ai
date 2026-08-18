import datetime as dt
import json
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.tradelens.api.serialization import finite_or_state, to_jsonable


def _roundtrip(value):
    """Strict: rejects Infinity/NaN, which json.dumps emits by default."""
    return json.loads(json.dumps(to_jsonable(value), allow_nan=False))


@pytest.mark.parametrize(
    "value,expected",
    [
        (np.int64(5), 5),
        (np.float64(1.5), 1.5),
        (np.bool_(True), True),
        (Decimal("2.50"), 2.5),
        (pd.NA, None),
        (pd.NaT, None),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (None, None),
    ],
)
def test_scalars_become_json_safe(value, expected):
    assert _roundtrip(value) == expected


def test_dates_become_iso_strings():
    assert _roundtrip(dt.date(2026, 8, 12)) == "2026-08-12"
    assert _roundtrip(
        dt.datetime(2026, 8, 12, 9, 30, tzinfo=dt.timezone.utc)
    ).startswith("2026-08-12T09:30:00")


def test_nested_containers_are_converted_throughout():
    payload = {"rows": [{"pnl": np.float64(1.0), "r": float("nan")}]}
    assert _roundtrip(payload) == {"rows": [{"pnl": 1.0, "r": None}]}


def test_dataframes_become_lists_of_records():
    df = pd.DataFrame({"asset": ["NQ"], "pnl": [np.float64(410.0)]})
    assert _roundtrip(df) == [{"asset": "NQ", "pnl": 410.0}]


def test_an_unknown_type_raises_rather_than_being_stringified():
    """Silently str()-ing an unexpected object ships a wrong value to the UI."""

    class Weird:
        pass

    with pytest.raises(TypeError):
        to_jsonable(Weird())


@pytest.mark.parametrize(
    "value,expected",
    [
        (2.5, (2.5, None)),
        (float("inf"), (None, "undefined_positive_infinity")),
        (float("-inf"), (None, "undefined_negative_infinity")),
        (float("nan"), (None, "undefined_nan")),
    ],
)
def test_finite_or_state_names_why_a_number_is_missing(value, expected):
    """An infinite profit factor means 'no losses to divide by'. Encoding that
    as a bare null loses the meaning the UI renders as ∞."""
    assert finite_or_state(value) == expected

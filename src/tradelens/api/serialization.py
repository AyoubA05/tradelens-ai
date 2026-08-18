"""One conversion from service values to JSON-safe values.

The service layer speaks pandas and numpy: metrics return DataFrames, and
individual figures come back as `numpy.float64`, `Decimal`, `pandas.NaT`, or a
non-finite float. `json.dumps` rejects some of those and, by default, emits
bare `Infinity` and `NaN` for the rest — tokens no strict JSON parser accepts.

The dangerous failure is not a crash. It is a silent coercion that turns an
undefined profit factor into 0.0 and renders a confident wrong number to a
trader. Unknown types therefore raise rather than being stringified.
"""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd

_PRIMITIVES = (str, bool, int)


def to_jsonable(value: object) -> object:
    """Convert `value` into something `json.dumps(..., allow_nan=False)` accepts.

    Non-finite floats become None; use `finite_or_state` where the reason a
    number is missing carries meaning.
    """
    if value is None or isinstance(value, _PRIMITIVES):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, Decimal):
        return to_jsonable(float(value))

    # numpy scalars: np.bool_ first — it is not a subclass of Python bool.
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return to_jsonable(float(value))

    # pandas nulls: NaT, NA. `pd.isna` on an array returns an array, so this is
    # guarded to scalars before being called.
    if value is pd.NaT or value is pd.NA:
        return None

    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()

    if isinstance(value, pd.DataFrame):
        return [to_jsonable(record) for record in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return [to_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.ndarray):
        return [to_jsonable(item) for item in value.tolist()]

    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]

    raise TypeError(
        f"{type(value).__name__} has no defined JSON representation. Add one "
        "here rather than letting it be stringified at the boundary."
    )


def finite_or_state(value: object) -> tuple[Optional[float], Optional[str]]:
    """Split a possibly-undefined number into (value, reason-it-is-undefined).

    Profit factor is infinite when there are no losses to divide by. That is a
    meaning, not a number, and a bare null cannot carry it — the UI renders it
    as ∞. Schemas pair an Optional[float] field with an Optional[str] state.
    """
    if value is None:
        return None, None
    number = float(value)
    if math.isnan(number):
        return None, "undefined_nan"
    if number == math.inf:
        return None, "undefined_positive_infinity"
    if number == -math.inf:
        return None, "undefined_negative_infinity"
    return number, None

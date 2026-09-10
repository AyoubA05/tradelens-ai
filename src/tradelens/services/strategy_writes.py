"""The Strategy Profile write path: locked, compare-and-swap, bounded.

The profile is the rulebook every AI review reads, so a write here is a change
to a prompt. Every write in this module holds four properties:

* **Serialized per owner.** The owner's `users` row is locked (SQLite:
  `BEGIN IMMEDIATE`) BEFORE the active profile is read — the same lock
  `api.jobs.enqueue_with_limit` takes. Without it, two first saves both read
  "no profile" and the owner ends up holding two active rows.
* **Compare-and-swap on a server-derived version, inside that transaction.**
  The version is the active row's `updated_at`, read under the lock. The
  caller only echoes back what it was given; it never supplies a version the
  server adopts. A mismatch raises `StaleProfile` before anything is written.
* **The version always moves.** Two writes inside one clock tick would
  otherwise share a version and let the stale one through (`_next_stamp`).
* **Nothing is truncated.** A value over its limit is refused, never cut.
  The trader has to shorten it themselves, so what is saved is what they wrote.

The Streamlit page still saves through `strategy.save_profile_and_mark_completed`,
which takes no lock. A save from there moves `updated_at`, so a web save based
on the older version is still refused here; the residual same-microsecond
window is recorded in the Phase 7 handoff and retires with Streamlit.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Dict, Iterator, List, Mapping, Optional

from sqlalchemy import text

from src.tradelens.db.models import Strategy, User
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ai_text_guard import MAX_PROMPT_TEXT_CHARS
from src.tradelens.services.corrections import _prompt_safe, repeated_corrections
from src.tradelens.services.strategy import (
    _PROFILE_FIELDS,
    _require_concrete_user_id,
    _to_dict,
)
from src.tradelens.services.strategy_playbook import REPEAT_THRESHOLD


class StaleProfile(Exception):
    """The profile changed since the caller read it. Nothing was written."""


class NoProfile(Exception):
    """The operation needs an active profile and the owner has none."""


class RulesFull(Exception):
    """Appending would push the target field past its limit. Nothing was written."""


class SuggestionNotFound(Exception):
    """No current repeated-correction group of this owner matches the key."""


class InvalidProfile(ValueError):
    """The write was refused before any database access.

    `problems` maps a field name to one fixed code, so the API can say which
    field is wrong without ever echoing the value back.
    """

    def __init__(self, problems: Dict[str, str]):
        super().__init__("invalid profile: " + ", ".join(sorted(problems)))
        self.problems = dict(problems)


NAME_MAX_CHARS = 100

# The prompt path bounds every profile string to MAX_PROMPT_TEXT_CHARS
# (`trade_analysis._sanitised_strategy`). Using the same constant, imported
# rather than copied, means a rule the trader saved is a rule the model is
# given in full.
FIELD_LIMITS: Mapping[str, int] = MappingProxyType(
    {
        f: (NAME_MAX_CHARS if f == "name" else MAX_PROMPT_TEXT_CHARS)
        for f in sorted(_PROFILE_FIELDS)
    }
)

# C0 controls and DEL, except tab and newline. `\r` is normalised to `\n`
# first (a pasted Windows line ending is a line ending, not content).
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

_INSIGHT_FIELD = "risk_rules"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_stamp(previous: Optional[str]) -> str:
    """A version strictly different from — and, when comparable, after — `previous`."""
    now = _now_iso()
    if previous is None or now > previous:
        return now
    try:
        bumped = datetime.fromisoformat(previous) + timedelta(microseconds=1)
    except ValueError:
        # A legacy stamp we cannot parse. `now` differs from it unless the
        # legacy text happens to equal a fresh ISO stamp, which it cannot
        # (it failed to parse as one).
        return now
    return bumped.isoformat()


def profile_revision(profile: Optional[dict]) -> Optional[str]:
    """The version a caller must echo back to write on top of `profile`."""
    return None if profile is None else profile.get("updated_at")


def over_limit(profile: Optional[dict]) -> List[str]:
    """Stored fields longer than their limit — shown, flagged, never truncated."""
    if not profile:
        return []
    return [
        f
        for f in sorted(_PROFILE_FIELDS)
        if isinstance(profile.get(f), str) and len(profile[f]) > FIELD_LIMITS[f]
    ]


@contextmanager
def _locked_session(owner: int) -> Iterator:
    """A session that holds the owner's write lock from before the first read."""
    db = SessionLocal()
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        else:
            db.query(User.id).filter(User.id == owner).with_for_update().one()
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _active_row(db, owner: int) -> Optional[Strategy]:
    return (
        db.query(Strategy)
        .filter(Strategy.user_id == owner, Strategy.is_active == 1)
        .first()
    )


def _check_revision(row: Optional[Strategy], expected: Optional[str]) -> None:
    current = None if row is None else row.updated_at
    if current != expected:
        raise StaleProfile()


def _normalise(fields: dict) -> dict:
    """Exactly the twelve fields, as bounded text or None. Refuses, never trims."""
    if not isinstance(fields, dict):
        raise InvalidProfile({"_body": "invalid"})
    problems: Dict[str, str] = {}
    for key in fields:
        if key not in _PROFILE_FIELDS:
            problems[str(key)[:64]] = "unknown_field"
    out = {}
    for key in sorted(_PROFILE_FIELDS):
        if key not in fields:
            problems[key] = "missing"
            continue
        value = fields[key]
        if value is not None and not isinstance(value, str):
            problems[key] = "not_text"
            continue
        value = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if _CONTROL.search(value):
            problems[key] = "invalid_characters"
            continue
        if len(value) > FIELD_LIMITS[key]:
            problems[key] = "too_long"
            continue
        out[key] = value or None
    if "name" not in problems and not out.get("name"):
        problems["name"] = "required"
    if problems:
        raise InvalidProfile(problems)
    return out


def _mark_completed_in_session(db, owner: int) -> None:
    user = db.query(User).filter(User.id == owner).first()
    if user is None:
        raise ValueError("No such account.")
    user.strategy_profile_completed = True


def save_profile(
    user_id: int, fields: dict, *, expected_revision: Optional[str]
) -> dict:
    """Replace the owner's active profile, and complete first run, atomically.

    `expected_revision` is the version the caller read (`None` when there was
    no profile). It is compared under the owner lock; a mismatch raises
    `StaleProfile` and writes nothing. Full replacement: every field is set.
    """
    owner = _require_concrete_user_id(user_id)
    clean = _normalise(fields)
    with _locked_session(owner) as db:
        row = _active_row(db, owner)
        _check_revision(row, expected_revision)
        if row is None:
            # A legacy owner may hold only inactive rows; reuse one rather than
            # adding another. Full replacement below overwrites every field.
            row = (
                db.query(Strategy)
                .filter(Strategy.user_id == owner)
                .order_by(Strategy.id)
                .first()
            )
            if row is None:
                row = Strategy(user_id=owner, name=clean["name"], created_at=_now_iso())
                db.add(row)
                db.flush()
        db.query(Strategy).filter(
            Strategy.user_id == owner, Strategy.id != row.id
        ).update({"is_active": 0}, synchronize_session=False)
        row.is_active = 1
        for key, value in clean.items():
            setattr(row, key, value)
        if row.created_at is None:
            row.created_at = _now_iso()
        row.updated_at = _next_stamp(row.updated_at)
        _mark_completed_in_session(db, owner)
        db.commit()
        db.refresh(row)
        return _to_dict(row)


def skip_first_run(user_id: int) -> None:
    """The "I don't have a defined strategy yet" exit: flag only, no profile."""
    owner = _require_concrete_user_id(user_id)
    with _locked_session(owner) as db:
        _mark_completed_in_session(db, owner)
        db.commit()


def insight_rule(group: dict) -> str:
    """The rule text for one repeated-correction group — built here, never sent."""
    return "• {}: prefer {} (corrected {}x in review)".format(
        _prompt_safe(group["field"]),
        _prompt_safe(group["user_value"]),
        int(group["count"]),
    )


def _lines(value: Optional[str]) -> List[str]:
    return [line.strip() for line in (value or "").split("\n")]


def insight_suggestions(user_id: int, profile: Optional[dict]) -> List[dict]:
    """This owner's repeated corrections not already present in risk rules."""
    owner = _require_concrete_user_id(user_id)
    present = set(_lines((profile or {}).get(_INSIGHT_FIELD)))
    out = []
    for group in repeated_corrections(threshold=REPEAT_THRESHOLD, user_id=owner):
        rule = insight_rule(group)
        if rule not in present:
            out.append(
                {
                    "field": group["field"],
                    "user_value": group["user_value"],
                    "count": int(group["count"]),
                    "rule": rule,
                }
            )
    return out


def append_repeated_correction(
    user_id: int,
    *,
    field: str,
    user_value: str,
    expected_revision: Optional[str],
) -> dict:
    """Add one repeated correction to risk rules — owner-scoped and idempotent.

    `field`/`user_value` are a lookup key only: the group is re-derived from
    this owner's own `Correction` rows and the rule text is built here. The
    target column is fixed. The trader's existing text is kept byte-for-byte;
    the rule is added on a new line after it.
    """
    owner = _require_concrete_user_id(user_id)
    match = next(
        (
            g
            for g in repeated_corrections(threshold=REPEAT_THRESHOLD, user_id=owner)
            if g["field"] == field and g["user_value"] == user_value
        ),
        None,
    )
    if match is None:
        raise SuggestionNotFound()
    rule = insight_rule(match)
    with _locked_session(owner) as db:
        row = _active_row(db, owner)
        if row is None:
            raise NoProfile()
        _check_revision(row, expected_revision)
        existing = getattr(row, _INSIGHT_FIELD) or ""
        if rule in _lines(existing):
            return _to_dict(row)
        combined = (
            "{}\n{}".format(existing.rstrip(), rule) if existing.strip() else rule
        )
        if len(combined) > FIELD_LIMITS[_INSIGHT_FIELD]:
            raise RulesFull()
        setattr(row, _INSIGHT_FIELD, combined)
        row.updated_at = _next_stamp(row.updated_at)
        db.commit()
        db.refresh(row)
        return _to_dict(row)

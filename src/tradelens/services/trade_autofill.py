"""Screenshot autofill: model output turned into reviewable draft suggestions.

Autofill is the journal's second AI consumer, so it inherits Phase 3E's cost
discipline rather than inventing a second one: the rate limit is checked
before any billable call (in the router, before `enqueue`), `Usage` is
recorded the instant the provider returns, and a failed job stays terminal.

Three properties are worth stating outright, because the happy path does not
show them:

1. **The image is the finalized object, never an upload.** Bytes arrive
   through `storage.read_owned_final_object`, which returns what
   `finalize_upload` promoted — decoded, capped and re-encoded by us. The
   model therefore only ever sees bytes we produced.
2. **Suggestions land on the draft, never on `trades`.** Nothing in this
   module writes a `Trade` row, and there is no code path from here to
   `create_trade`. Creation stays with `POST /v1/trades`, where the allowlist,
   the fingerprint and every server-side derivation still apply.
3. **The allowlist is the filter, and it runs before anything is stored.** A
   field the model invents — or a derived field it volunteers — is dropped in
   `filter_suggestions`, so it has nowhere to go.

No Streamlit imports here.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable, Optional, Union

from src.tradelens.api import storage
from src.tradelens.services import drafts
from src.tradelens.services.ai_autofill import (
    _is_truthy_flag as is_truthy_flag,  # one truthiness rule, not two
)
from src.tradelens.services.ai_autofill import map_analysis_to_form
from src.tradelens.services.ai_overlay import descriptive_section, parse_trade_overlay

# The autocheck confidence policy: one rule, not a second copy of it. It
# lives in services/autocheck_policy (not here, and not re-derived), and
# ui/components/ai_autofill_review.py re-exports the same functions so the
# Streamlit review panel and this service always agree on which fields
# pre-check.
from src.tradelens.services.autocheck_policy import should_autocheck
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.vision import (
    ScreenshotAnalysisError,
    analyze_screenshot_v3,
    check_screenshot_quality,
)

# One paid Opus vision call per request, so the same ceiling shape as
# summaries: generous enough that a trader never feels it, bounded enough that
# an authenticated account cannot mint unlimited billable jobs.
MAX_AUTOFILLS_PER_WINDOW = 20
AUTOFILL_WINDOW_HOURS = 24

JOB_KIND = "trade_autofill"

# Which screenshot the draft's current suggestions were read from. One draft
# per owner means the suggestion set is superseded by the next run, so the
# poll needs to know whose readings these are; the enqueue idempotency key is
# the screenshot, so per owner a screenshot id names exactly one job.
SUGGESTIONS_SOURCE_KEY = "ai_suggestions_screenshot_id"
SUGGESTIONS_JOB_KEY = "ai_suggestions_job_id"

# THE write allowlist. Every field here is one a chart screenshot can actually
# evidence, and every one is a field `POST /v1/trades` itself accepts from a
# human. Nothing derived is here, and nothing can be added by the model:
# `filter_suggestions` intersects against this set before a single suggestion
# is stored.
#
# `entry_time` is in the wire set but excluded from `AUTOFILL_TRADE_FIELDS`
# below for the same reason `CREATABLE_TRADE_FIELDS` excludes it: it is not a
# `Trade` column, so "subset of the create allowlist" is a statement about
# columns, not wire fields.
AUTOFILL_SUGGESTION_FIELDS = frozenset(
    {
        "asset",
        "timeframe",
        "htf_bias",
        "bias",
        "direction",
        "entry_time",
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "pnl",
        "liquidity_sweep",
        "fvg_used",
        "order_block_used",
        "bos",
        "choch",
    }
)
AUTOFILL_TRADE_FIELDS = AUTOFILL_SUGGESTION_FIELDS - {"entry_time"}

# Descriptive SMC flags -> the draft's 0/1 columns. Only a true-like flag ever
# produces a suggestion: "the model did not see a sweep" and "there was no
# sweep" are different claims, and suggesting `0` would assert the second.
_FLAG_FIELDS = ("liquidity_sweep", "fvg_used", "order_block_used", "bos", "choch")

# Overlay fields carried straight through, with their per-field confidence.
_OVERLAY_FIELDS = (
    "direction",
    "entry_price",
    "stop_price",
    "tp_price",
    "exit_price",
)

# Extension the promoted object always has. `finalize_upload` normalises every
# image to one content type, so this is not a guess.
_FINAL_SUFFIX = ".png"


class AutofillUnavailable(Exception):
    """Raised when autofill cannot run at all — no image, or an unusable one.

    Terminal by construction: the job runner marks the job failed and the
    idempotency key stops a resubmit from re-spending on the same screenshot.
    """


def _suggestion(value, confidence, field: str) -> dict:
    return {
        "value": value,
        "confidence": confidence,
        "autocheck": should_autocheck(field, confidence),
    }


def filter_suggestions(suggestions: dict) -> dict:
    """Keep only fields on the autofill write allowlist.

    This is the guard the whole feature rests on and it runs *before* storage,
    not after: a field the model invented, and a server-derived field it
    volunteered, are both simply absent from the result. Neither reaches the
    draft, so neither can be carried into a create.
    """
    if not isinstance(suggestions, dict):
        return {}
    return {
        field: value
        for field, value in suggestions.items()
        if field in AUTOFILL_SUGGESTION_FIELDS
    }


def build_suggestions(analysis: Optional[dict]) -> dict:
    """Turn one v3 analysis into `{field: {value, confidence, autocheck}}`.

    The mapping reuses the existing normalisers (`map_analysis_to_form` for
    the descriptive section, `parse_trade_overlay` for the visible markup), so
    a value that reaches a suggestion has already been through the same
    validation Streamlit's panel applies. The result is filtered on the way
    out regardless.
    """
    if not isinstance(analysis, dict):
        return {}

    descriptive = descriptive_section(analysis)
    overlay = parse_trade_overlay(analysis)
    built: dict = {}

    mapped = map_analysis_to_form(descriptive).prefill
    for source, field in (
        ("asset", "asset"),
        ("timeframe", "timeframe"),
        ("htf_bias", "htf_bias"),
        # The vision contract's LTF `bias` is the trade's `bias` column.
        ("ltf_bias", "bias"),
    ):
        if mapped.get(source) is not None:
            built[field] = _suggestion(mapped[source], None, field)

    for flag in _FLAG_FIELDS:
        if is_truthy_flag(descriptive.get(flag)):
            built[flag] = _suggestion(1, None, flag)

    for field in _OVERLAY_FIELDS:
        value = getattr(overlay, field, None)
        if value is not None:
            built[field] = _suggestion(value, overlay.confidence.get(field), field)

    if overlay.pnl is not None:
        built["pnl"] = _suggestion(overlay.pnl, None, "pnl")
    if overlay.entry_time_approx:
        built["entry_time"] = _suggestion(
            overlay.entry_time_approx,
            overlay.confidence.get("entry_time"),
            "entry_time",
        )

    return filter_suggestions(built)


def analyse_image(
    image_path: Union[str, Path],
    *,
    on_usage: Callable[[object], None],
) -> dict:
    """Quality-check then analyse one local image, returning raw v3 output.

    `on_usage` is passed through to the provider call rather than applied to
    the return value: it must fire the instant the provider answers, because
    everything after that can raise and a call that was billed must still be
    visible in cost tracking.
    """
    quality = check_screenshot_quality(image_path)
    if not quality.usable:
        # Refused before any billable call: an image the local pre-check
        # cannot open is not going to be readable by the model either.
        raise AutofillUnavailable("that screenshot could not be read")
    analysis, _usage = analyze_screenshot_v3(image_path, {}, None, on_usage=on_usage)
    return analysis


def suggest_from_screenshot(
    user_id: int,
    screenshot_id: int,
    *,
    job_id: int,
    on_usage: Callable[[object], None],
) -> dict:
    """Run autofill for one owned screenshot and save the suggestions.

    The bytes are the promoted, re-encoded object — see
    `storage.read_owned_final_object`. They are materialised to a temp file
    only because the vision client takes a path; this is not a second image
    path, because these bytes already passed `validate_and_normalise` and were
    written by us. The file is removed on every exit.
    """
    owner = require_user_id(user_id)
    data = storage.read_owned_final_object(owner, screenshot_id)
    if not data:
        raise AutofillUnavailable("that screenshot could not be read")

    handle, temp_path = tempfile.mkstemp(suffix=_FINAL_SUFFIX)
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
        try:
            analysis = analyse_image(temp_path, on_usage=on_usage)
        except ScreenshotAnalysisError as exc:
            raise AutofillUnavailable(str(exc)) from exc
    finally:
        try:
            os.unlink(temp_path)
        except OSError:  # pragma: no cover — best effort, never masks a result
            pass

    return save_suggestions_to_draft(
        owner,
        build_suggestions(analysis),
        screenshot_id=screenshot_id,
        job_id=job_id,
    )


def save_suggestions_to_draft(
    user_id: int, suggestions: dict, *, screenshot_id: int, job_id: int
) -> dict:
    """Persist a suggestion set beside the owner's draft, and return it.

    Merged into the existing draft rather than replacing it: the trader may
    have typed something while the job ran, and their values are theirs. The
    suggestions sit in their own key, so an unreviewed suggestion is never
    mistaken for a confirmed value — and this function writes to
    `trade_drafts` only, so no number of runs can produce a `trades` row.

    Filtered again here even though `build_suggestions` already filtered: this
    is the function that touches storage, so this is where the guarantee has
    to hold.

    `screenshot_id` is REQUIRED and is stored beside the suggestions, because
    this function supersedes: there is one draft per owner, so a second
    autofill run overwrites the first one's suggestions. Without the
    provenance key, a poll of the first job would answer with the second
    chart's readings and nothing would say so — a trader could not tell which
    screenshot a value came from. `SUGGESTIONS_SOURCE_KEY` is what the poll
    compares against the job it was actually asked about.
    """
    owner = require_user_id(user_id)
    kept = filter_suggestions(suggestions)
    drafts.save_autofill_suggestions(
        owner,
        kept,
        screenshot_id=screenshot_id,
        job_id=job_id,
    )
    return kept

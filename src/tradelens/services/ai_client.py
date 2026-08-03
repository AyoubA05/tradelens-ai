"""
Single wrapper around the Anthropic SDK — the ONLY place AI calls happen.

Centralises adaptive thinking + effort, prompt caching, image encoding, cost
accounting, and DEMO_MODE so feature services (vision.py, journal.py,
grading.py, weekly.py, patterns.py, debrief.py, partner.py) never import
`anthropic` directly.

Streamlit-free. Every public call returns a `(content, Usage)` tuple where
`content` is either a string or a typed `AIUnavailable` the UI renders gracefully.

One model, no routing: every call uses `config.ANTHROPIC_MODEL_ID`
(claude-opus-5). Callers cannot select a model, and a refusal is surfaced as a
typed `AIUnavailable` rather than silently retried on a different model.

Pricing (per 1M tokens): opus-5 $5/$25. Prompt-cache tokens bill separately from
`input_tokens` — writes at 1.25x the input rate (5-minute ephemeral TTL), reads
at 0.1x — and all four buckets are folded into `Usage.estimated_cost_usd`.
"""

from __future__ import annotations

import base64
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from src.tradelens.config import ANTHROPIC_MODEL_ID, resolve_anthropic_key, settings
from src.tradelens.services.corrections import build_correction_few_shot

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost table — per 1,000,000 tokens. One entry, because there is one model.
# ---------------------------------------------------------------------------
_COST_PER_M: dict[str, dict[str, float]] = {
    ANTHROPIC_MODEL_ID: {"input": 5.0, "output": 25.0},
}
# Prompt-cache multipliers, relative to the model's base input rate.
#   • Writing a cache entry costs a premium: 1.25x for the default 5-minute
#     ephemeral TTL (2x would apply to a 1-hour TTL, which we do not use —
#     _build_system() only ever sets {"type": "ephemeral"} with no ttl).
#   • Reading a cache entry is ~10% of the input rate.
# Missing either factor understates real spend on the cached Strategy Profile
# path, which is exactly the call we repeat most.
_CACHE_WRITE_FACTOR = 1.25
_CACHE_READ_FACTOR = 0.1

# Beta header + param enabling the model to think adaptively with a summary.
_THINKING = {"type": "adaptive", "display": "summarized"}


@dataclass
class Usage:
    """Token and cost metadata returned alongside every API response."""

    model: str
    tokens_in: int
    tokens_out: int
    total_tokens: int
    estimated_cost_usd: float
    latency_s: float
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    thinking_summary: Optional[str] = None
    refused: bool = False

    def __str__(self) -> str:
        return (
            f"{self.model}  in={self.tokens_in} out={self.tokens_out} "
            f"cache_r={self.cache_read_tokens} cache_w={self.cache_creation_tokens} "
            f"cost=${self.estimated_cost_usd:.5f}  {self.latency_s:.2f}s"
        )


@dataclass
class AIUnavailable:
    """Typed result returned when the AI cannot answer (refusal, missing key, error).

    Feature services and pages check `isinstance(result, AIUnavailable)` and render
    a friendly message instead of a stack trace.
    """

    reason: str
    category: Optional[str] = None


_PARSE_ERROR_MSG = (
    "The AI returned a malformed response (invalid JSON). Please try again."
)


class AIParseError(Exception):
    """Raised when an AI response cannot be parsed as JSON.

    Carries a friendly, user-facing message — feature services surface this
    instead of leaking a raw json.JSONDecodeError / stack trace to the page.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_transient_error(exc: Exception) -> bool:
    """True only for retryable transport failures (network, timeout, rate limit, 5xx).

    Those degrade gracefully to a friendly "temporarily unavailable" message.
    Everything else — a bad kwarg, an invalid model, an auth/config problem, or an
    unexpected SDK break — is a real bug and must surface, not be disguised as a
    transient outage. A swallowed ``TypeError`` from a stale SDK (an unexpected
    ``output_config`` kwarg) is exactly what once hid the vision call failing.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    try:
        import anthropic
    except Exception:  # noqa: BLE001 — a missing/broken package is not transient
        return False
    if isinstance(
        exc,
        (
            anthropic.APIConnectionError,  # includes APITimeoutError
            anthropic.RateLimitError,  # 429
            anthropic.InternalServerError,  # 5xx / overloaded
        ),
    ):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def _has_key() -> bool:
    return bool(resolve_anthropic_key())


def has_api_key() -> bool:
    """Public: True when an Anthropic API key is configured.

    Powers the Settings → AI status indicator. Reads the same source as every
    AI call, so the badge reflects what would actually happen.
    """
    return _has_key()


def _get_client():
    """Construct an Anthropic client. Imported lazily so DEMO_MODE / tests that
    mock this function don't require the `anthropic` package to be installed."""
    import anthropic

    return anthropic.Anthropic(
        api_key=resolve_anthropic_key(),
        timeout=settings.anthropic_timeout,
        max_retries=settings.anthropic_max_retries,
    )


def _estimate_cost(
    model: str,
    tokens_in: int,
    tokens_out: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    """Estimated USD for one call, covering all four billed token buckets.

    ``tokens_in`` is the *uncached remainder* the API reports — cache creation
    and cache read tokens are billed separately, at their own multipliers, and
    are not included in ``input_tokens``. Summing only input + output silently
    drops the cache-write premium on every first call of a cached prompt.
    """
    rates = _COST_PER_M.get(model, {"input": 0.0, "output": 0.0})
    return (
        tokens_in * rates["input"]
        + cache_creation_tokens * rates["input"] * _CACHE_WRITE_FACTOR
        + cache_read_tokens * rates["input"] * _CACHE_READ_FACTOR
        + tokens_out * rates["output"]
    ) / 1_000_000


def _extract_text(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def _extract_thinking(resp) -> Optional[str]:
    parts = [b.thinking for b in resp.content if getattr(b, "type", None) == "thinking"]
    return "\n".join(p for p in parts if p) or None


def _build_usage(resp, model: str, t0: float) -> Usage:
    u = resp.usage
    tokens_in = getattr(u, "input_tokens", 0) or 0
    tokens_out = getattr(u, "output_tokens", 0) or 0
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(u, "cache_creation_input_tokens", 0) or 0
    # Full prompt size = uncached input + cache writes + cache reads. Reporting
    # only `input_tokens` under-counts a cached call by the whole cached prefix.
    return Usage(
        model=getattr(resp, "model", model) or model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_tokens=tokens_in + cache_creation + cache_read + tokens_out,
        estimated_cost_usd=_estimate_cost(
            model, tokens_in, tokens_out, cache_read, cache_creation
        ),
        latency_s=round(time.monotonic() - t0, 3),
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        thinking_summary=_extract_thinking(resp),
    )


def _corrections_block(scope: Optional[str] = None) -> str:
    """Fetch the token-budgeted <past_corrections> block, or '' on any error.

    Wrapped defensively so a DB hiccup never breaks an AI call — corrections are
    optional context, not a hard dependency.
    """
    try:
        return build_correction_few_shot(scope=scope) or ""
    except Exception:  # noqa: BLE001 — corrections are best-effort context
        return ""


def _build_system(system_message: str, few_shot: Optional[str], cache_system: bool):
    """Assemble the system field. When `cache_system`, return a content-block list
    carrying a cache_control breakpoint (used for the repeated Strategy Profile)."""
    text = system_message or ""
    if few_shot:
        text = f"{text}\n\n{few_shot}".strip()
    if not text:
        return None
    if cache_system:
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    return text


def _complete(
    messages: list,
    *,
    system_message: str,
    effort: Optional[str],
    cache_system: bool,
    few_shot: Optional[str],
    demo_response: Optional[str],
    max_tokens: int,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Core call path shared by chat(), vision() and converse()."""
    chosen = ANTHROPIC_MODEL_ID

    # Correction memory: inject the trader's past overrides into EVERY call.
    # Deterministic + DB-only (no API), so it runs even in DEMO_MODE.
    corrections = _corrections_block()
    combined_few_shot = "\n\n".join(p for p in (few_shot, corrections) if p) or None
    system = _build_system(system_message, combined_few_shot, cache_system)

    # DEMO_MODE: never touch the network.
    if settings.demo_mode:
        content = (
            demo_response
            if demo_response is not None
            else "[DEMO MODE] AI output disabled."
        )
        return content, Usage(chosen, 0, 0, 0, 0.0, 0.0)

    if not _has_key():
        return (
            AIUnavailable("Anthropic API key not configured.", category="config"),
            Usage(chosen, 0, 0, 0, 0.0, 0.0),
        )

    kwargs: dict = {
        "max_tokens": max_tokens,
        "messages": messages,
        "thinking": _THINKING,
        "output_config": {"effort": effort or settings.effort_default},
    }
    if system is not None:
        kwargs["system"] = system

    t0 = time.monotonic()
    try:
        client = _get_client()
        resp = client.messages.create(model=chosen, **kwargs)
        # A refusal is final: there is no fallback model to retry on, so surface
        # it as a typed result the UI renders instead of a stack trace.
        if getattr(resp, "stop_reason", None) == "refusal":
            usage = _build_usage(resp, chosen, t0)
            usage.refused = True
            return (
                AIUnavailable(
                    "The AI declined to analyze this request.", category="refusal"
                ),
                usage,
            )

        return _extract_text(resp), _build_usage(resp, chosen, t0)
    except Exception as exc:  # noqa: BLE001 — classify, then degrade or surface
        _log.exception("AI call failed (model=%s)", chosen)
        # Only genuine transport failures degrade to a friendly typed result.
        # Real bugs (bad kwarg, invalid model, auth/config) re-raise so they are
        # immediately visible instead of masquerading as a transient outage.
        if not _is_transient_error(exc):
            raise
        # The exception itself is logged above, never surfaced: a user-facing
        # string must not carry SDK internals, request payloads or the API key.
        return (
            AIUnavailable(
                "The AI service is temporarily unavailable. "
                "Please try again shortly.",
                category="network",
            ),
            Usage(chosen, 0, 0, 0, 0.0, round(time.monotonic() - t0, 3)),
        )


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------


def encode_image(path: Union[str, Path], max_dimension: int = 1024) -> str:
    """Resize (if needed) and base64-encode a local image as JPEG for the vision API."""
    from PIL import Image  # lazy import — not needed for text-only calls

    img = Image.open(Path(path))
    w, h = img.size
    if max(w, h) > max_dimension:
        ratio = max_dimension / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def load_prompt(name: str) -> str:
    """Load a versioned prompt template from prompts/{name}.txt (stripped)."""
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def parse_ai_json(text: str):
    """Parse an AI response as JSON, tolerating a ```json code fence.

    Returns the decoded object/list. Raises AIParseError (friendly message) on
    anything unparseable — the single typed error for malformed AI JSON.
    """
    import json

    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise AIParseError(_PARSE_ERROR_MSG) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chat(
    user_message: str,
    system_message: str = "",
    *,
    effort: Optional[str] = None,
    response_format: Optional[
        dict
    ] = None,  # accepted for caller compatibility; JSON is prompt-driven
    cache_system: bool = False,
    few_shot: Optional[str] = None,
    demo_response: Optional[str] = None,
    max_tokens: int = 8192,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Send a text prompt to Claude Opus 5. Returns (content_or_AIUnavailable, Usage)."""
    messages = [{"role": "user", "content": user_message}]
    return _complete(
        messages,
        system_message=system_message,
        effort=effort,
        cache_system=cache_system,
        few_shot=few_shot,
        demo_response=demo_response,
        max_tokens=max_tokens,
    )


def vision(
    image_path: Union[str, Path],
    user_message: str,
    system_message: str = "",
    *,
    effort: Optional[str] = None,
    response_format: Optional[dict] = None,  # accepted for caller compatibility
    cache_system: bool = False,
    few_shot: Optional[str] = None,
    demo_response: Optional[str] = None,
    max_dimension: int = 1024,
    max_tokens: int = 8192,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Send an image + text prompt to Claude Opus 5 vision.

    Returns (content_or_AIUnavailable, Usage)."""
    # DEMO_MODE short-circuits before any image work.
    if settings.demo_mode:
        chosen = ANTHROPIC_MODEL_ID
        content = (
            demo_response
            if demo_response is not None
            else "[DEMO MODE] AI output disabled."
        )
        return content, Usage(chosen, 0, 0, 0, 0.0, 0.0)

    image_b64 = encode_image(image_path, max_dimension)
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_b64,
            },
        },
        {"type": "text", "text": user_message},
    ]
    messages = [{"role": "user", "content": content}]
    return _complete(
        messages,
        system_message=system_message,
        effort=effort,
        cache_system=cache_system,
        few_shot=few_shot,
        demo_response=demo_response,
        max_tokens=max_tokens,
    )


def converse(
    messages: list,
    system_message: str = "",
    *,
    effort: Optional[str] = None,
    cache_system: bool = False,
    few_shot: Optional[str] = None,
    demo_response: Optional[str] = None,
    max_tokens: int = 8192,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Multi-turn chat: caller supplies the full role-tagged `messages` list.

    Routes through the same core path as chat()/vision(), so correction memory is
    injected centrally and DEMO_MODE / refusal handling apply uniformly. The
    caller is responsible for the message list shape (image blocks, ordering)."""
    return _complete(
        messages,
        system_message=system_message,
        effort=effort,
        cache_system=cache_system,
        few_shot=few_shot,
        demo_response=demo_response,
        max_tokens=max_tokens,
    )

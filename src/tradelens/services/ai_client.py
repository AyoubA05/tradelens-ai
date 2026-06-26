"""
Single wrapper around the Anthropic SDK — the ONLY place AI calls happen.

Centralises model routing, adaptive thinking + effort, prompt caching, image
encoding, refusal fallback, cost accounting, and DEMO_MODE so feature services
(vision.py, journal.py, grading.py, weekly.py, patterns.py, partner.py) never
import `anthropic` directly.

Streamlit-free. Every public call returns a `(content, Usage)` tuple where
`content` is either a string or a typed `AIUnavailable` the UI renders gracefully.

Model routing (configured in config.py):
    claude-fable-5    primary — vision, journal, weekly, patterns, partner
    claude-haiku-4-5  grading pre-pass only (pass model=settings.model_grading)
    claude-opus-4-8   refusal fallback

Pricing (per 1M tokens): fable-5 $10/$50, opus-4-8 $5/$25, haiku-4-5 $1/$5;
cache reads bill at ~0.1x the input rate.
"""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from src.tradelens.config import settings
from src.tradelens.services.corrections import build_correction_few_shot

# ---------------------------------------------------------------------------
# Cost table — per 1,000,000 tokens
# ---------------------------------------------------------------------------
_COST_PER_M: dict[str, dict[str, float]] = {
    "claude-fable-5": {"input": 10.0, "output": 50.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}
_CACHE_READ_FACTOR = 0.1  # cached input tokens bill at ~10% of the input rate

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
    thinking_summary: Optional[str] = None
    refused: bool = False

    def __str__(self) -> str:
        return (
            f"{self.model}  in={self.tokens_in} out={self.tokens_out} "
            f"cache={self.cache_read_tokens} cost=${self.estimated_cost_usd:.5f}  "
            f"{self.latency_s:.2f}s"
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


def _has_key() -> bool:
    return bool(settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY"))


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
        api_key=settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY"),
        timeout=settings.anthropic_timeout,
        max_retries=settings.anthropic_max_retries,
    )


def _estimate_cost(
    model: str, tokens_in: int, tokens_out: int, cache_read_tokens: int = 0
) -> float:
    rates = _COST_PER_M.get(model, {"input": 0.0, "output": 0.0})
    return (
        tokens_in * rates["input"]
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
    return Usage(
        model=getattr(resp, "model", model) or model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_tokens=tokens_in + tokens_out,
        estimated_cost_usd=_estimate_cost(model, tokens_in, tokens_out, cache_read),
        latency_s=round(time.monotonic() - t0, 3),
        cache_read_tokens=cache_read,
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
    model: Optional[str],
    effort: Optional[str],
    cache_system: bool,
    few_shot: Optional[str],
    demo_response: Optional[str],
    max_tokens: int,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Core call path shared by chat() and vision()."""
    chosen = model or settings.model_primary

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
        # Refusal → retry once with the fallback model (spec rule).
        if getattr(resp, "stop_reason", None) == "refusal":
            resp = client.messages.create(model=settings.model_fallback, **kwargs)
            if getattr(resp, "stop_reason", None) == "refusal":
                usage = _build_usage(resp, settings.model_fallback, t0)
                usage.refused = True
                return (
                    AIUnavailable(
                        "The AI declined to analyze this request.", category="refusal"
                    ),
                    usage,
                )
            return _extract_text(resp), _build_usage(resp, settings.model_fallback, t0)

        return _extract_text(resp), _build_usage(resp, chosen, t0)
    except Exception as exc:  # noqa: BLE001 — any transport/API error → typed result
        return (
            AIUnavailable(
                "The AI service is temporarily unavailable "
                f"({type(exc).__name__}). Please try again shortly.",
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
    model: Optional[str] = None,
    effort: Optional[str] = None,
    response_format: Optional[
        dict
    ] = None,  # accepted for caller compatibility; JSON is prompt-driven
    cache_system: bool = False,
    few_shot: Optional[str] = None,
    demo_response: Optional[str] = None,
    max_tokens: int = 8192,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Send a text prompt to Claude. Returns (content_or_AIUnavailable, Usage)."""
    messages = [{"role": "user", "content": user_message}]
    return _complete(
        messages,
        system_message=system_message,
        model=model,
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
    model: Optional[str] = None,
    effort: Optional[str] = None,
    response_format: Optional[dict] = None,  # accepted for caller compatibility
    cache_system: bool = False,
    few_shot: Optional[str] = None,
    demo_response: Optional[str] = None,
    max_dimension: int = 1024,
    max_tokens: int = 8192,
) -> tuple[Union[str, AIUnavailable], Usage]:
    """Send an image + text prompt to Claude vision. Returns (content_or_AIUnavailable, Usage)."""
    # DEMO_MODE short-circuits before any image work.
    if settings.demo_mode:
        chosen = model or settings.model_primary
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
        model=model,
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
    model: Optional[str] = None,
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
        model=model,
        effort=effort,
        cache_system=cache_system,
        few_shot=few_shot,
        demo_response=demo_response,
        max_tokens=max_tokens,
    )

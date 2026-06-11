"""
Thin wrapper around the OpenAI SDK.

Centralises model names, retries, timeout, image encoding, and cost accounting
so vision.py / journal.py / grading.py never import openai directly.

All functions are Streamlit-free and return a (content, Usage) tuple so callers
decide how to present latency and cost information.
"""
import base64
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from openai import AuthenticationError as OpenAIAuthError, OpenAI

from src.tradelens.config import settings

# ---------------------------------------------------------------------------
# Cost estimates — verify at https://openai.com/pricing before billing review
# ---------------------------------------------------------------------------
_COST_PER_1K: dict[str, dict[str, float]] = {
    "gpt-4o":       {"input": 0.005,    "output": 0.015},
    "gpt-4o-mini":  {"input": 0.000150, "output": 0.000600},
}


@dataclass
class Usage:
    """Token and cost metadata returned alongside every API response."""
    model: str
    tokens_in: int
    tokens_out: int
    total_tokens: int
    estimated_cost_usd: float
    latency_s: float

    def __str__(self) -> str:
        return (
            f"{self.model}  in={self.tokens_in} out={self.tokens_out} "
            f"cost=${self.estimated_cost_usd:.5f}  {self.latency_s:.2f}s"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_client() -> OpenAI:
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key is missing. Add OPENAI_API_KEY to your .env file.")
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries,
    )


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    rates = _COST_PER_1K.get(model, {"input": 0.0, "output": 0.0})
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1000


def _build_usage(resp, model: str, t0: float) -> Usage:
    u = resp.usage
    return Usage(
        model=model,
        tokens_in=u.prompt_tokens,
        tokens_out=u.completion_tokens,
        total_tokens=u.prompt_tokens + u.completion_tokens,
        estimated_cost_usd=_estimate_cost(model, u.prompt_tokens, u.completion_tokens),
        latency_s=round(time.monotonic() - t0, 3),
    )


def encode_image(path: Union[str, Path], max_dimension: int = 1024) -> str:
    """
    Resize (if needed) and base64-encode a local image for the vision API.

    Kept at module level so vision.py can import it independently if needed.
    Converts to JPEG at quality=85 for cost control.
    """
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
    """
    Load a versioned prompt template from prompts/{name}.txt

    Keeps prompt text out of Python files so diffs are readable and
    prompt iterations are independently trackable.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(
    user_message: str,
    system_message: str = "",
    model: Optional[str] = None,
    response_format: Optional[dict] = None,
) -> tuple[str, Usage]:
    """
    Send a text prompt to the chat completions endpoint.

    Returns (content_str, Usage).
    Use response_format={"type": "json_object"} to enforce structured output.
    """
    m = model or settings.model_text
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_message})

    kwargs: dict = {"model": m, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format

    client = _get_client()
    t0 = time.monotonic()
    try:
        resp = client.chat.completions.create(**kwargs)
    except OpenAIAuthError:
        raise ValueError("OpenAI API key is missing. Add OPENAI_API_KEY to your .env file.")
    return resp.choices[0].message.content, _build_usage(resp, m, t0)


def vision(
    image_path: Union[str, Path],
    user_message: str,
    system_message: str = "",
    model: Optional[str] = None,
    response_format: Optional[dict] = None,
    max_dimension: int = 1024,
) -> tuple[str, Usage]:
    """
    Send an image + text to the vision endpoint.

    Returns (content_str, Usage).
    image_path must point to a local file; it is resized + JPEG-encoded before sending.
    """
    m = model or settings.model_vision
    image_b64 = encode_image(image_path, max_dimension)

    content = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_b64}",
                "detail": "high",
            },
        },
        {"type": "text", "text": user_message},
    ]
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": content})

    kwargs: dict = {"model": m, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format

    client = _get_client()
    t0 = time.monotonic()
    try:
        resp = client.chat.completions.create(**kwargs)
    except OpenAIAuthError:
        raise ValueError("OpenAI API key is missing. Add OPENAI_API_KEY to your .env file.")
    return resp.choices[0].message.content, _build_usage(resp, m, t0)


# ---------------------------------------------------------------------------
# Smoke test — run manually: python -m src.tradelens.services.openai_client
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Sending smoke-test chat message…")
    content, usage = chat("Reply with exactly: smoke test OK")
    print(f"Response : {content}")
    print(f"Usage    : {usage}")

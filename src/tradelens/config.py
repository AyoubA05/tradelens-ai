import os
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

# On Streamlit Cloud, ANTHROPIC_API_KEY comes from st.secrets, not env vars.
# Inject into os.environ before pydantic-settings reads it so the Settings
# class picks it up without any structural changes.
#
# Gated on `"streamlit" in sys.modules` rather than a bare `import streamlit`:
# this module is imported by db/session.py, which every services/ and api/
# module reaches transitively through Settings. An unconditional import here
# would drag Streamlit into every service and API process — exactly the
# "NO streamlit imports inside services/ or db/" rule this file does not
# live in but every one of those modules imports through. Checking
# sys.modules first still finds the bridge inside the actual Streamlit app
# (the `streamlit run` process has already imported the package by the time
# any page reaches this import), it just stops a non-Streamlit process from
# being the one that imports it for the first time.
if "streamlit" in sys.modules:
    try:
        import streamlit as st

        _cloud_key = st.secrets.get("ANTHROPIC_API_KEY", None)
        if _cloud_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", str(_cloud_key))
    except Exception:
        pass


# The one Anthropic model TradeLens uses, everywhere. Screenshot analysis,
# autofill, grading, journal summaries, pattern analysis, weekly recaps, daily
# debriefs and AI Partner chat all run on Claude Opus 5.
#
# This constant is the single source of truth for the model ID. It is
# deliberately NOT a Settings field: an env-overridable model would let a
# deployment silently route traffic to a different (or non-existent) model,
# which is exactly what the single-model rule exists to prevent. There is no
# per-feature model selection and no automatic fallback to another model.
ANTHROPIC_MODEL_ID = "claude-opus-5"


class Settings(BaseSettings):
    # Anthropic — all AI calls route through services/ai_client.py on
    # ANTHROPIC_MODEL_ID above.
    anthropic_api_key: str = ""
    effort_default: str = "medium"
    anthropic_timeout: int = 120
    anthropic_max_retries: int = 2

    # DEMO_MODE: when true, ai_client returns cached/mock output — zero API spend.
    demo_mode: bool = False

    # DB (kept for future wiring; session.py still hardcodes the URL for now)
    database_url: str = "sqlite:///./data/tradelens.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def resolve_anthropic_key() -> str:
    """Resolve the Anthropic API key from any configured source, at call time.

    Order: pydantic settings (env / .env at import) → live ``os.environ`` →
    ``st.secrets``. The import-time bridge above only fires if a Streamlit context
    already existed when config was first imported — on localhost that ordering is
    not guaranteed, which is why a key sitting in ``.streamlit/secrets.toml`` still
    produced "AI unavailable" on the Pattern Insights / Weekly Review pages
    (Bug 5). Re-checking ``st.secrets`` here closes that gap, and any key found is
    mirrored into ``os.environ`` so the Anthropic SDK and every code path agree on
    one source of truth.
    """
    key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    if key:
        return str(key)
    try:
        import streamlit as st

        secret = st.secrets.get("ANTHROPIC_API_KEY", None)
        if secret:
            os.environ.setdefault("ANTHROPIC_API_KEY", str(secret))
            return str(secret)
    except Exception:  # noqa: BLE001 — missing secrets file is expected off-cloud
        pass
    return ""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# On Streamlit Cloud, ANTHROPIC_API_KEY comes from st.secrets, not env vars.
# Inject into os.environ before pydantic-settings reads it so the Settings
# class picks it up without any structural changes.
try:
    import streamlit as st
    _cloud_key = st.secrets.get("ANTHROPIC_API_KEY", None)
    if _cloud_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", str(_cloud_key))
except Exception:
    pass


class Settings(BaseSettings):
    # Anthropic — all AI calls route through services/ai_client.py
    anthropic_api_key: str = ""
    model_primary: str = "claude-fable-5"     # vision, journal, weekly, patterns, partner
    model_grading: str = "claude-haiku-4-5"   # cheap grading pre-pass only
    model_fallback: str = "claude-opus-4-8"   # refusal fallback
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

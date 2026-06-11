import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# On Streamlit Cloud, OPENAI_API_KEY comes from st.secrets, not env vars.
# Inject into os.environ before pydantic-settings reads it so the Settings
# class picks it up without any structural changes.
try:
    import streamlit as st
    _cloud_key = st.secrets.get("OPENAI_API_KEY", None)
    if _cloud_key:
        os.environ.setdefault("OPENAI_API_KEY", str(_cloud_key))
except Exception:
    pass


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""
    model_vision: str = "gpt-4o"
    model_text: str = "gpt-4o-mini"
    openai_timeout: int = 60
    openai_max_retries: int = 2

    # DB (kept for future wiring; session.py still hardcodes the URL for now)
    database_url: str = "sqlite:///./data/tradelens.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

"""One accessor for every deployment setting.

Two modules previously disagreed about where settings live, and the
disagreement was invisible until it mattered:

    ui/components/auth.py       environment, then st.secrets, then default
    services/password_reset.py  environment only

On Streamlit Cloud, secrets are exposed through ``st.secrets`` and are NOT
placed in the process environment. So a single configured
``TRADELENS_SESSION_SECRET`` was read by auth.py and missed by
password_reset.py, which then fell back to a random per-process key. The two
modules signed tokens with unrelated material while appearing to share one
setting — and because both still "worked" in isolation, nothing failed loudly.
Reset tokens simply stopped verifying after a restart.

Resolution order is fixed and identical for every caller:
environment, then ``st.secrets``, then the supplied default.

Values are returned to callers and never logged.
"""

from __future__ import annotations

import os

# Every deployment setting this project reads. Listed so a test can assert no
# module reaches for one of these names via os.getenv directly, which is how
# the original split happened.
SETTING_NAMES = (
    "DATABASE_URL",
    "TRADELENS_SESSION_SECRET",
    "TRADELENS_INVITE_CODE",
    "SIGNUP_MODE",
    "TRADELENS_SMTP_HOST",
    "TRADELENS_SMTP_PORT",
    "TRADELENS_SMTP_USER",
    "TRADELENS_SMTP_PASSWORD",
    "TRADELENS_SMTP_FROM",
    "APP_ORIGIN",
    "SITE_ORIGIN",
)


def read_setting(name: str, default: str = "") -> str:
    """Resolve one setting: environment, then st.secrets, then the default.

    A blank or missing value falls through to the next source, so an empty
    environment variable does not mask a configured secret.
    """
    value = os.getenv(name)
    if value:
        return str(value)
    try:
        import streamlit as st

        secret = st.secrets.get(name, None)
        if secret:
            return str(secret)
    except Exception:  # noqa: BLE001 — no secrets file is normal off-Cloud
        pass
    return default

"""API-only settings. Read from the environment; never hardcoded, never logged."""

from __future__ import annotations

import os

from src.tradelens.settings_source import read_setting


def service_secrets() -> list:
    """Accepted signing secrets, current first.

    Two are supported so ``TL_SERVICE_SECRET`` can be rotated without downtime:
    deploy the new secret as the current one and keep the old in
    ``TL_SERVICE_SECRET_PREVIOUS`` until every caller has been redeployed, then
    clear it. A rotation that required both sides to change at the same instant
    would mean an outage every time the secret changed.
    """
    candidates = [
        os.getenv("TL_SERVICE_SECRET", ""),
        os.getenv("TL_SERVICE_SECRET_PREVIOUS", ""),
    ]
    return [s for s in candidates if s]


def is_production() -> bool:
    return os.getenv("TL_ENV", "development").lower() == "production"


def _production_database_is_remote() -> bool:
    value = read_setting("DATABASE_URL")
    return value.startswith(("postgresql://", "postgres://"))


def validate_api_runtime() -> None:
    """Refuse an insecure or ephemeral production API configuration."""
    if not is_production():
        return
    invalid = []
    secrets = service_secrets()
    if not secrets or any(len(secret.encode("utf-8")) < 32 for secret in secrets):
        invalid.append("TL_SERVICE_SECRET")
    if not _production_database_is_remote():
        invalid.append("DATABASE_URL")
    if invalid:
        raise RuntimeError(
            "invalid production configuration: " + ", ".join(sorted(set(invalid)))
        )


def validate_worker_runtime() -> None:
    """The worker must never poll an ephemeral local database in production."""
    if is_production() and not _production_database_is_remote():
        raise RuntimeError("invalid production configuration: DATABASE_URL")


def r2_config() -> dict:
    """Object-storage settings. Consumed by the storage adapter in a later phase."""
    return {
        "account_id": os.getenv("R2_ACCOUNT_ID", ""),
        "access_key_id": os.getenv("R2_ACCESS_KEY_ID", ""),
        "secret_access_key": os.getenv("R2_SECRET_ACCESS_KEY", ""),
        "bucket": os.getenv("R2_BUCKET", ""),
    }

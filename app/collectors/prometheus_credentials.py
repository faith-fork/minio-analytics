from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class PrometheusCredentialError(RuntimeError):
    """Raised when encrypted Prometheus credentials cannot be used safely."""


def _fernet() -> Fernet:
    key = os.getenv("MINIO_ANALYTICS_CREDENTIALS_KEY", "").strip()
    if not key:
        raise PrometheusCredentialError(
            "Prometheus authentication is configured but MINIO_ANALYTICS_CREDENTIALS_KEY is not set"
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise PrometheusCredentialError(
            "MINIO_ANALYTICS_CREDENTIALS_KEY must be a valid Fernet key"
        ) from exc


def encrypt_credentials(auth_type: str, credentials: dict[str, str] | None) -> str | None:
    if auth_type == "none":
        return None
    if auth_type not in {"basic", "bearer"} or not credentials:
        raise PrometheusCredentialError("Invalid Prometheus authentication configuration")
    payload = json.dumps(
        {"auth_type": auth_type, "credentials": credentials},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_credentials(auth_type: str, encrypted: str | None) -> dict[str, str] | None:
    if auth_type == "none":
        return None
    if auth_type not in {"basic", "bearer"} or not encrypted:
        raise PrometheusCredentialError("Prometheus credentials are missing or invalid")
    try:
        payload: Any = json.loads(_fernet().decrypt(encrypted.encode("ascii")))
    except (InvalidToken, ValueError, TypeError, UnicodeEncodeError) as exc:
        raise PrometheusCredentialError(
            "Prometheus credentials cannot be decrypted; check the configured encryption key"
        ) from exc
    if not isinstance(payload, dict) or payload.get("auth_type") != auth_type:
        raise PrometheusCredentialError("Stored Prometheus credentials have an invalid format")
    credentials = payload.get("credentials")
    if not isinstance(credentials, dict) or not all(
        isinstance(value, str) for value in credentials.values()
    ):
        raise PrometheusCredentialError("Stored Prometheus credentials have an invalid format")
    return credentials


def build_authorization_header(auth_type: str, encrypted: str | None) -> str | None:
    credentials = decrypt_credentials(auth_type, encrypted)
    if credentials is None:
        return None
    if auth_type == "basic":
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        if any(ord(char) < 32 or ord(char) == 127 for char in username + password) or ":" in username:
            raise PrometheusCredentialError("Prometheus Basic Auth credentials contain invalid characters")
        if not username:
            raise PrometheusCredentialError("Prometheus Basic Auth username is missing")
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}"
    token = credentials.get("token", "")
    if not token:
        raise PrometheusCredentialError("Prometheus Bearer Token is missing")
    if not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token):
        raise PrometheusCredentialError("Prometheus Bearer Token contains invalid token characters")
    return f"Bearer {token}"

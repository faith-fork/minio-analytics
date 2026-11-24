from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from app.collectors.prometheus_credentials import (
    PrometheusCredentialError,
    build_authorization_header,
    decrypt_credentials,
    encrypt_credentials,
)


def test_basic_credentials_are_encrypted_and_recoverable(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", key)
    secret = {"username": "metrics-reader", "password": "do-not-store-plaintext"}
    encrypted = encrypt_credentials("basic", secret)

    assert encrypted is not None
    assert "do-not-store-plaintext" not in encrypted
    assert decrypt_credentials("basic", encrypted) == secret
    assert build_authorization_header("basic", encrypted).startswith("Basic ")


def test_bearer_token_is_encrypted_and_recoverable(monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", Fernet.generate_key().decode("ascii"))
    encrypted = encrypt_credentials("bearer", {"token": "sensitive-token-value"})

    assert encrypted is not None
    assert "sensitive-token-value" not in encrypted
    assert decrypt_credentials("bearer", encrypted) == {"token": "sensitive-token-value"}
    assert build_authorization_header("bearer", encrypted) == "Bearer sensitive-token-value"


def test_no_auth_does_not_require_an_encryption_key(monkeypatch):
    monkeypatch.delenv("MINIO_ANALYTICS_CREDENTIALS_KEY", raising=False)

    assert encrypt_credentials("none", None) is None
    assert build_authorization_header("none", None) is None


def test_configured_auth_fails_closed_without_encryption_key(monkeypatch):
    monkeypatch.delenv("MINIO_ANALYTICS_CREDENTIALS_KEY", raising=False)

    with pytest.raises(PrometheusCredentialError, match="KEY is not set"):
        encrypt_credentials("basic", {"username": "reader", "password": "secret"})


def test_invalid_encryption_key_is_rejected(monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", "not-a-fernet-key")

    with pytest.raises(PrometheusCredentialError, match="valid Fernet key"):
        encrypt_credentials("bearer", {"token": "secret"})


def test_auth_type_mismatch_is_rejected(monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", Fernet.generate_key().decode("ascii"))
    encrypted = encrypt_credentials("basic", {"username": "reader", "password": "secret"})

    with pytest.raises(PrometheusCredentialError, match="invalid format"):
        decrypt_credentials("bearer", encrypted)



def test_location_config_repr_never_exposes_authorization_header():
    from app.config.loader import LocationConfig

    location = LocationConfig(
        id="site-a",
        name="Site A",
        prometheus_url="https://prometheus.example:9443",
        clusters=(),
        auth_header="Bearer do-not-print-this-token",
    )

    assert "do-not-print-this-token" not in repr(location)
    assert "Bearer " not in repr(location)

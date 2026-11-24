from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.database.database import initialize_database, transaction
from scripts.rotate_prometheus_credentials import main


def _seed_connection(connection_id: str, encrypted: str) -> None:
    with transaction() as connection:
        connection.execute(
            "INSERT INTO locations(id, name, enabled) VALUES(?, ?, 1)",
            (f"location-{connection_id}", f"Location {connection_id}"),
        )
        connection.execute(
            """INSERT INTO prometheus_connections
               (connection_id, location_id, protocol, hostname, port, auth_type, auth_secret_encrypted)
               VALUES(?, ?, 'https', ?, 9443, 'bearer', ?)""",
            (connection_id, f"location-{connection_id}", f"{connection_id}.example", encrypted),
        )


def test_rotation_reencrypts_all_credentials_and_audits(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "rotate.db"))
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    encrypted = Fernet(old_key).encrypt(b'{"auth_type":"bearer","credentials":{"token":"secret-token"}}').decode()
    initialize_database()
    _seed_connection("prom-a", encrypted)
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_OLD_KEY", old_key.decode())
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", new_key.decode())

    assert main() == 0

    with transaction() as connection:
        row = connection.execute(
            "SELECT auth_secret_encrypted FROM prometheus_connections WHERE connection_id='prom-a'"
        ).fetchone()
        audit = connection.execute(
            "SELECT COUNT(*) AS n FROM settings_audit "
            "WHERE setting_key='prometheus_credentials_key_rotation'"
        ).fetchone()["n"]
    plaintext = Fernet(new_key).decrypt(row["auth_secret_encrypted"].encode())
    assert b"secret-token" in plaintext
    try:
        Fernet(old_key).decrypt(row["auth_secret_encrypted"].encode())
    except InvalidToken:
        pass
    else:
        raise AssertionError("Rotated ciphertext still decrypts with the old key")
    assert audit == 1


def test_rotation_failure_leaves_every_credential_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "rotate-failure.db"))
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    valid = Fernet(old_key).encrypt(b'{"auth_type":"bearer","credentials":{"token":"secret-token"}}').decode()
    initialize_database()
    _seed_connection("prom-a", valid)
    _seed_connection("prom-b", "not-valid-fernet-ciphertext")
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_OLD_KEY", old_key.decode())
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", new_key.decode())

    assert main() == 1

    with transaction() as connection:
        rows = connection.execute(
            "SELECT connection_id, auth_secret_encrypted FROM prometheus_connections ORDER BY connection_id"
        ).fetchall()
    assert [(row["connection_id"], row["auth_secret_encrypted"]) for row in rows] == [
        ("prom-a", valid),
        ("prom-b", "not-valid-fernet-ciphertext"),
    ]


def test_rotation_fails_closed_when_authenticated_credential_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("MINIO_ANALYTICS_DB", str(tmp_path / "rotate-missing.db"))
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    valid = Fernet(old_key).encrypt(
        b'{"auth_type":"bearer","credentials":{"token":"secret-token"}}'
    ).decode()
    initialize_database()
    _seed_connection("prom-a", valid)
    _seed_connection("prom-b", valid)
    with transaction() as connection:
        connection.execute(
            "UPDATE prometheus_connections SET auth_secret_encrypted=NULL "
            "WHERE connection_id='prom-b'"
        )
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_OLD_KEY", old_key.decode())
    monkeypatch.setenv("MINIO_ANALYTICS_CREDENTIALS_KEY", new_key.decode())

    assert main() == 1

    with transaction() as connection:
        rows = connection.execute(
            "SELECT connection_id, auth_secret_encrypted FROM prometheus_connections "
            "ORDER BY connection_id"
        ).fetchall()
    assert [(row["connection_id"], row["auth_secret_encrypted"]) for row in rows] == [
        ("prom-a", valid),
        ("prom-b", None),
    ]

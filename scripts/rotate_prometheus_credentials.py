from __future__ import annotations

import os
import sys

from cryptography.fernet import Fernet, InvalidToken

from app.database.database import initialize_database, transaction


def main() -> int:
    old_key = os.getenv("MINIO_ANALYTICS_CREDENTIALS_OLD_KEY", "").strip()
    new_key = os.getenv("MINIO_ANALYTICS_CREDENTIALS_KEY", "").strip()
    if not old_key or not new_key:
        print(
            "Set MINIO_ANALYTICS_CREDENTIALS_OLD_KEY and "
            "MINIO_ANALYTICS_CREDENTIALS_KEY in the protected environment.",
            file=sys.stderr,
        )
        return 2
    try:
        old_fernet = Fernet(old_key.encode("ascii"))
        new_fernet = Fernet(new_key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        print("One or both credential encryption keys are invalid.", file=sys.stderr)
        return 2
    if old_key == new_key:
        print("The old and new credential encryption keys are identical.", file=sys.stderr)
        return 2

    initialize_database()
    try:
        with transaction() as connection:
            rows = connection.execute(
                """SELECT connection_id, auth_secret_encrypted
                   FROM prometheus_connections
                   WHERE auth_type != 'none' AND auth_secret_encrypted IS NOT NULL
                   ORDER BY connection_id"""
            ).fetchall()
            rotated = []
            for row in rows:
                try:
                    plaintext = old_fernet.decrypt(row["auth_secret_encrypted"].encode("ascii"))
                except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
                    raise RuntimeError(
                        "At least one credential could not be decrypted with the old key; "
                        "no credentials were changed."
                    ) from exc
                rotated.append((new_fernet.encrypt(plaintext).decode("ascii"), row["connection_id"]))
            for encrypted, connection_id in rotated:
                connection.execute(
                    """UPDATE prometheus_connections
                       SET auth_secret_encrypted=?,
                           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                       WHERE connection_id=?""",
                    (encrypted, connection_id),
                )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Credential encryption key rotation completed for {len(rotated)} connection(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

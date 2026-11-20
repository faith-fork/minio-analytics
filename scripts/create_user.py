from __future__ import annotations

import argparse
import getpass
import re

from app.auth.security import hash_password
from app.database.database import initialize_database, transaction

_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a MinIO Analytics application user."
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=("admin", "viewer"), default="viewer")
    args = parser.parse_args()

    username = args.username.strip().lower()
    if not _USERNAME.fullmatch(username):
        parser.error(
            "Username must be 3-64 characters: lowercase letters, digits, '.' '_' or '-'"
        )

    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords do not match")

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        parser.error(str(exc))

    initialize_database()
    try:
        with transaction() as connection:
            connection.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, args.role),
            )
    except Exception as exc:
        if "UNIQUE constraint failed: users.username" in str(exc):
            parser.error(f"User already exists: {username}")
        raise

    print(f"Created {args.role} user: {username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

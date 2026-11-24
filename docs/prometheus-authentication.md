# Prometheus connection authentication

MinIO Analytics supports optional authentication for each Prometheus connection.

## Supported modes

- **None** (default): no credentials are required. HTTP or HTTPS may be used.
- **Basic Authentication**: username and password. HTTPS is mandatory.
- **Bearer Token**: token. HTTPS is mandatory.

Credentials are never accepted in the Prometheus URL. HTTPS certificate-chain and hostname verification remain mandatory and cannot be disabled. The client continues to use the validated, address-pinned transport and rejects redirects.

## Configure the encryption key

The application encrypts Prometheus credentials before writing them to SQLite using Fernet authenticated encryption. The encryption key is external to the database and repository.

Generate a key in a trusted environment:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Set the resulting value as `MINIO_ANALYTICS_CREDENTIALS_KEY` in the protected application environment (for the lab service, `/etc/minio-analytics/web.env`). Restrict that file to the service administrator, for example mode `0600`. Do not commit the key, put it in a command-line argument, or include it in support bundles.

The key is not required while every connection uses authentication type `none`. If an authenticated connection exists, the key must be available to the web application and every collector process that loads the connection from SQLite.

**Back up the key separately from the database.** If the key is lost, encrypted credentials cannot be recovered; configure replacement Prometheus credentials through the Master Admin screen.

## Credential updates

Use the Prometheus Connections screen and choose **Authentication** for a connection. Enter the new secret; the existing secret is intentionally never displayed. MinIO Analytics tests discovery against the configured endpoint before replacing the stored credential. Choosing **None** removes authentication.

The API returns only the authentication type and whether a credential is configured. It never returns a password, bearer token, Authorization header, or ciphertext.

## Encryption-key rotation

The rotation utility re-encrypts all configured Prometheus secrets in one SQLite transaction. It requires the old and new keys through protected environment variables:

- `MINIO_ANALYTICS_CREDENTIALS_OLD_KEY`: current/old Fernet key.
- `MINIO_ANALYTICS_CREDENTIALS_KEY`: replacement/new Fernet key.

Recommended procedure:

1. Take and verify a database backup.
2. Schedule a short maintenance window and stop application/collector processes that use the database.
3. Set both key variables in a protected environment; do not put either key in shell history or command-line arguments.
4. Run `python scripts/rotate_prometheus_credentials.py` from the repository root using the application virtual environment.
5. Confirm the utility reports the number of rotated connections.
6. Remove the old-key variable, leave only the new `MINIO_ANALYTICS_CREDENTIALS_KEY`, and restart the application and collectors.
7. Verify an authenticated connection test and a collection run before closing the maintenance window.

The script validates that every encrypted credential can be decrypted before updating any row. A decryption failure aborts the transaction, leaving all stored ciphertext unchanged.

## Operational notes

- No-auth connections continue to work without an encryption key.
- Basic Auth and Bearer Token are rejected on HTTP, both at the API boundary and in the Prometheus transport.
- The current HTTPS trust configuration uses the system CA trust store. Custom/private CA bundles and mTLS client certificates are not part of this increment.
- Never include credentials in URLs, logs, audit records, screenshots, or diagnostic output.

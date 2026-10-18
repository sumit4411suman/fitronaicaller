# Backup and restore

* Backups use SQLite's online backup API, so they are consistent even while the app is running (WAL mode).
* With `backup.encrypt` on (default) a passphrase of at least 8 characters is required; the file is AES-256-GCM encrypted
  with a scrypt-derived key (`.sabk`). The header (timestamp, app version, SHA-256, size) is authenticated. Without a
  passphrase the backup is a plain `.db` plus a `.json` metadata file.
* Files live in `<data dir>\backups`; `backup.retention_count` (default 10) oldest-first pruning.
* **Verify** decrypts (if needed), checks the SHA-256 and runs `PRAGMA integrity_check`.
* **Restore** requires typing `RESTORE`, verifies first, writes a `pre-restore-<timestamp>.db` safety copy next to the live
  database, atomically replaces the database, removes stale `-wal/-shm` files and re-runs migrations. Restart the app afterwards.
* Only files inside the backups directory are accepted (no arbitrary paths).

Manual alternative: close the app and copy `%LOCALAPPDATA%\SellAgent\sellagent.db` (plus `-wal`/`-shm` if present).
Keep the passphrase somewhere safe: an encrypted backup cannot be recovered without it.

Automated evidence: `tests/integration/test_backup_and_migrations.py` (encrypted round trip, wrong passphrase rejected,
confidentiality of the ciphertext, retention, restore, path rejection).

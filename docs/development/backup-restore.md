# Local PostgreSQL backup and restore verification

M4 provides an operator CLI for **trusted local PostgreSQL databases and trusted self-created archives**. It is not an upload/import API, an automated off-site backup service or a production disaster-recovery certification. PostgreSQL documents that restoring an archive can execute SQL chosen by its source administrators; never restore participant-provided archives. See the official [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) and [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html) references.

## Creating and checking a backup

Use PostgreSQL 18 client tools matching the supported server, or the tools already installed in the local PostgreSQL container. `DATABASE_URL` is read from the environment and must name a loopback PostgreSQL database without search-path/query overrides. Passwords are passed only in the child environment, never command arguments or diagnostic output. Before dumping or creating/restoring a target, the CLI compares `system_identifier`, database and role from native SQL and the `psql` tool connection. An unavailable or mismatched identity fails closed before mutation; the operator needs permission to read `pg_control_system()`. A container name alone is not trusted as evidence of the target server. The `--container` option assumes PostgreSQL's port 5432 inside that container.

```sh
# Export DATABASE_URL in your terminal using the local development configuration.
# Pick a private directory OUTSIDE the Git checkout, preferably on encrypted storage.
.venv/bin/python -m praxioj_api.backup backup /private/tmp/praxioj-private-backups --container praxioj-db-1
.venv/bin/python -m praxioj_api.backup verify /private/tmp/praxioj-private-backups/praxioj_TIMESTAMP_ID.dump --container praxioj-db-1
```

Without `--container`, `psql`, `pg_dump` and `pg_restore` must be on PATH. Native database connections and pool waits are capped at five seconds, lock waits at five seconds, and statements/tool processes at the configured operation timeout (120 seconds by default). No custom crypto or compression algorithm is implemented. `pg_dump` produces its standard compressed custom-format archive; a companion JSON manifest records creation time, byte count and SHA-256. A `pg_restore --list` check verifies the archive structure before backup success is reported. The checksum detects accidental corruption relative to that manifest; it is not a signature against a malicious operator replacing both files.

Directories must be owned by the current OS user with mode 0700, files mode 0600. Symlink files, overwrites, permissive modes and paths inside the repository are refused. Files are flushed before success. Tool failure or timeout returns nonzero with a controlled error code and removes files created by that failed invocation. An abruptly killed process can leave an incomplete orphan file: do not use it without a matching verified manifest. Operators must monitor exit status and inspect interrupted operations.

Archives contain password hashes, session records, conversations and other private data. **They are not encrypted by this CLI.** Use a separately configured and verified encrypted filesystem or established backup encryption tool and key management before storing sensitive data. Current tests verify POSIX permissions and integrity, not host disk encryption or Native Windows ACLs. No actual participant data should be entered into this preview.

## Restore into a new quarantined database

```sh
.venv/bin/python -m praxioj_api.backup restore-test /private/tmp/praxioj-private-backups/praxioj_TIMESTAMP_ID.dump --container praxioj-db-1
```

The command verifies the manifest/checksum/archive, creates a new random `praxioj_restore_<uuid>` database from `template0`, and restores with `--single-transaction`, `--exit-on-error`, `--no-owner` and `--no-privileges`. It never chooses an existing application DB, uses `--clean`, overwrites a database or deletes a volume. It requires local database-creation privileges. Tests use only synthetic dedicated source/target databases; the ordinary application volume is retained.

Before archive SQL runs, the new database receives a `praxioj_restore_quarantine` marker. API startup and worker startup/claim checks reject that marker. No promotion or marker-removal command is provided. The successful restore validates the current M4 migration revision (`0007_operations`), required tables and columns, reports restored row counts and revokes all restored authentication sessions. Schema/foreign-key restore errors fail the operation. Counts describe the restored snapshot; they are not compared with an unlocked, concurrently changing source. Supported archival upgrades need a separate migration/recovery procedure.

Restore failure leaves only the newly created target for operator review and reports its safe generated database name. It attempts to preserve the quarantine marker and revoke any restored sessions; an unavailable DB can prevent those cleanup transactions, so never connect a serving process to a failed target. An existing-name collision does not alter that database. Only the tests automatically remove their own newly created synthetic databases.

## Retention, erasure and recovery approval

```sh
.venv/bin/python -m praxioj_api.backup prune /private/tmp/praxioj-private-backups --retention-days 7
```

Pruning accepts 1–30 days, defaults to seven, and processes at most 1,000 recognized manifests per invocation. It verifies the matching archive, refuses path traversal/symlinks, and removes only the verified pair. Other files are left alone. Repeat bounded batches as needed. No scheduler is installed; the operator must schedule and monitor backups and pruning independently of AI workers.

A backup is a historical snapshot. Deleting an account or expiring its Trace today does not erase yesterday's archive. Restoring without the latest erasure decisions can resurrect deleted content and old access. Therefore restored databases remain blocked. Before any future reviewed recovery workflow can remove that barrier, an operator must:

1. Obtain the authoritative **latest** account-erasure/Trace-expiry decisions from a separately protected deletion ledger, not only the old snapshot. Current audit events provide the pseudonymous IDs/counts to export into such a ledger; automated off-site ledger replication is not implemented.
2. Replay deletions, run retention against the current time, revoke credentials, quarantine pending/running work and reconcile any uncertain provider effects without replay.
3. Validate schema, reference integrity, application behavior and quotas in isolation; review the destination, access policy and backup age before separate promotion approval.

Keep that external ledger for at least the longest backup lifetime, and do not configure audit retention shorter than the interval needed to capture deletion decisions. Default 90-day audit retention exceeds the maximum 30-day archive retention; an operator can shorten audits and must account for that conflict. Missing or stale deletion evidence blocks promotion. This milestone implements the quarantine barrier and synthetic restore verification, **not** automatic deletion from all historical copies or a production recovery orchestrator.

## Validation and optimization

`tests/ops/test_backup.py` covers private file modes, repository/path restrictions, corruption before restore, bounded pruning, unsupported source configuration, real custom-format backup and restore, restored-session revocation, incompatible-schema quarantine and existing-database collision protection. For real tests set `PRAXIOJ_TEST_DATABASE_URL` and, if host clients are unavailable, `PRAXIOJ_TEST_BACKUP_CONTAINER`. CI uses its disposable PostgreSQL service container.

Reviewed; no justified optimization: standard PostgreSQL clients stream archive bytes directly to/from private files, hashing reads 1 MiB chunks, and restore uses a single transaction for the small local verification workload. Compression/concurrency tuning without realistic database-size and I/O measurements would create unsupported performance claims. Large datasets, WAL/PITR, encrypted remote storage, backup scheduling/alerts and recovery-time objectives remain future work.

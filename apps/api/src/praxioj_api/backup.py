"""Operator-only PostgreSQL backup and quarantined restore checks.

Only trusted archives produced by the operator belong here: PostgreSQL archives
can contain executable SQL. This module is never exposed through an HTTP route.
"""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

QUARANTINE_TABLE = "praxioj_restore_quarantine"
FORMAT = "praxioj-postgres-backup/1"
IDENTITY_SQL = "SELECT json_build_object('cluster_id', system_identifier::text, 'database', current_database(), 'role', current_user) FROM pg_control_system()"


class BackupError(RuntimeError):
    """Safe operation code only; never includes credentials or PostgreSQL stderr."""
    def __init__(self, code, *, database=None):
        super().__init__(code)
        self.code, self.database = code, database


def assert_not_restored_database(engine):
    if inspect(engine).has_table(QUARANTINE_TABLE):
        raise RuntimeError("Restored database is quarantined; serving or executing it is prohibited")


def private_directory(value):
    path = Path(value).absolute()
    if path.is_symlink():
        raise BackupError("unsafe_backup_directory")
    path = path.resolve()
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        for ancestor in (start, *start.parents):
            if (ancestor / ".git").exists() and (path == ancestor or ancestor in path.parents):
                raise BackupError("backups_must_be_outside_repository")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
        raise BackupError("backup_directory_requires_owner_only_access")
    return path


def open_private(path, mode):
    flags = os.O_NOFOLLOW | (os.O_RDONLY if mode == "rb" else os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
        os.close(fd)
        raise BackupError("backup_file_requires_owner_only_access")
    return os.fdopen(fd, mode)


def digest_file(path):
    digest, size = sha256(), 0
    with open_private(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class PostgresBackup:
    def __init__(self, database_url, *, container=None, timeout_seconds=120, expected_revision="0008_judge_execution"):
        try:
            self.url = make_url(database_url)
        except Exception:
            raise BackupError("invalid_database_configuration") from None
        if self.url.drivername != "postgresql+psycopg" or self.url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise BackupError("backup_requires_local_postgresql")
        if not self.url.database or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.url.database):
            raise BackupError("unsupported_database_name")
        if self.url.query:
            raise BackupError("backup_requires_whole_database_without_query_options")
        if container and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container):
            raise BackupError("invalid_container_name")
        if not 1 <= timeout_seconds <= 3600:
            raise BackupError("invalid_backup_timeout")
        self.container, self.timeout = container, timeout_seconds
        self.expected_revision = expected_revision

    def engine(self, database=None, **kwargs):
        return create_engine(self.url.set(database=database or self.url.database),
            connect_args={"connect_timeout": 5, "options": f"-cstatement_timeout={int(self.timeout * 1000)} -clock_timeout=5000"},
            pool_timeout=5, pool_pre_ping=True, **kwargs)

    def verify_cluster(self, database=None):
        """Native SQL and PostgreSQL tools must reach the same cluster/DB/role.

        In particular, a Docker container name is not proof that its PostgreSQL
        server is the native URL's server. Identity reads are operator-only and
        require pg_control_system permission; unavailable checks fail closed.
        """
        engine = self.engine(database)
        try:
            with engine.connect() as connection:
                native = connection.execute(text(IDENTITY_SQL)).scalar_one()
            encoded = self.run("psql", ["-X", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1",
                "--command=" + IDENTITY_SQL], database=database, stdout=subprocess.PIPE)
            if len(encoded) > 4096:
                raise BackupError("backup_cluster_identity_unavailable")
            tool_identity = json.loads(encoded)
            if not isinstance(native, dict) or set(native) != {"cluster_id", "database", "role"} or native != tool_identity:
                raise BackupError("backup_cluster_identity_mismatch")
        except BackupError:
            raise
        except Exception:
            raise BackupError("backup_cluster_identity_unavailable") from None
        finally:
            engine.dispose()

    def run(self, program, args, *, database=None, stdin=None, stdout=None):
        # Password stays in the child environment, never command arguments/logs.
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        if self.url.password is not None:
            env["PGPASSWORD"] = self.url.password
        connection = [f"--host={'127.0.0.1' if self.container else self.url.host}",
            f"--port={5432 if self.container else (self.url.port or 5432)}", f"--username={self.url.username}"]
        if database is not False:
            connection += [f"--dbname={database or self.url.database}"]
        command = [program, *connection, *args]
        if self.container:
            command = ["docker", "exec", "-i", "--env", "PGPASSWORD", self.container, *command]
        try:
            result = subprocess.run(command, env=env, stdin=stdin, stdout=stdout if stdout is not None else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, check=True, timeout=self.timeout)
            return result.stdout
        except (OSError, subprocess.SubprocessError):
            raise BackupError(f"{program}_failed") from None

    def backup(self, directory):
        folder = private_directory(directory)
        self.verify_cluster()
        engine = self.engine()
        try:
            assert_not_restored_database(engine)
        finally:
            engine.dispose()
        stem = "praxioj_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid4().hex
        archive = folder / (stem + ".dump")
        manifest = folder / (stem + ".json")
        created_archive = created_manifest = False
        try:
            with open_private(archive, "wb") as handle:
                created_archive = True
                self.run("pg_dump", ["--format=custom", "--no-owner", "--no-privileges"], stdout=handle)
                handle.flush()
                os.fsync(handle.fileno())
            with open_private(archive, "rb") as handle:
                self.run("pg_restore", ["--list"], database=False, stdin=handle)
            digest, size = digest_file(archive)
            metadata = {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                        "sha256": digest, "size_bytes": size, "archive": archive.name,
                        "encryption": "none; requires an operator-managed encrypted storage volume"}
            with open_private(manifest, "wb") as handle:
                created_manifest = True
                handle.write(json.dumps(metadata, separators=(",", ":")).encode())
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            if created_archive:
                archive.unlink(missing_ok=True)
            if created_manifest:
                manifest.unlink(missing_ok=True)
            raise
        return {"archive": str(archive), "manifest": str(manifest), "sha256": digest, "size_bytes": size}

    def verify(self, archive):
        archive = Path(archive).absolute()
        private_directory(archive.parent)
        manifest = archive.with_suffix(".json")
        try:
            with open_private(manifest, "rb") as handle:
                encoded = handle.read(8193)
            if len(encoded) > 8192:
                raise ValueError()
            metadata = json.loads(encoded)
            if metadata["format"] != FORMAT or metadata["archive"] != archive.name:
                raise ValueError()
            digest, size = digest_file(archive)
            if digest != metadata["sha256"] or size != metadata["size_bytes"]:
                raise ValueError()
        except (ValueError, KeyError, TypeError, OSError):
            raise BackupError("backup_integrity_failed") from None
        with open_private(archive, "rb") as handle:
            self.run("pg_restore", ["--list"], database=False, stdin=handle)
        return metadata

    def restore_test(self, archive):
        metadata = self.verify(archive)
        self.verify_cluster()
        name = "praxioj_restore_" + uuid4().hex
        admin = self.engine("postgres", isolation_level="AUTOCOMMIT")
        target = None
        created_target = False
        try:
            with admin.connect() as connection:
                # The generated identifier is never caller-controlled. Existing
                # databases are not dropped, cleaned, selected or overwritten.
                connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
                created_target = True
            target = self.engine(name)
            # Install the serving/execution barrier before any archive SQL runs.
            with target.begin() as connection:
                connection.execute(text(f"CREATE TABLE {QUARANTINE_TABLE} (created_at timestamptz NOT NULL, archive_sha256 varchar(64) NOT NULL)"))
                connection.execute(text(f"INSERT INTO {QUARANTINE_TABLE} VALUES (CURRENT_TIMESTAMP, :digest)"), {"digest": metadata["sha256"]})
            self.verify_cluster(name)
            with open_private(Path(archive), "rb") as handle:
                self.run("pg_restore", ["--no-owner", "--no-privileges", "--single-transaction", "--exit-on-error"],
                         database=name, stdin=handle)
            with target.begin() as connection:
                from .models import Base
                from . import job_models, quota_models, retention_models, judge_models  # noqa: F401 — register complete platform schema
                inspector = inspect(connection)
                tables = set(inspector.get_table_names())
                required = set(Base.metadata.tables) | {"alembic_version"}
                if not required <= tables:
                    raise BackupError("restored_schema_incomplete")
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                if revision != self.expected_revision:
                    raise BackupError("restored_schema_revision_requires_review")
                for table in Base.metadata.tables.values():
                    if not {column.name for column in table.columns} <= {column["name"] for column in inspector.get_columns(table.name)}:
                        raise BackupError("restored_schema_columns_incomplete")
                # Count restored data instead of comparing with a separately
                # queried source that may have changed during pg_dump's snapshot.
                counts = {table: connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
                          for table in sorted(required - {"alembic_version"})}
                revoked = connection.execute(text("DELETE FROM auth_sessions")).rowcount
            return {"database": name, "status": "quarantined", "revision": revision,
                    "restored_counts": counts, "revoked_auth_sessions": revoked,
                    "archive_sha256": metadata["sha256"]}
        except Exception:
            # A failed restore is deliberately retained for operator inspection;
            # no existing database or application volume is ever destroyed here.
            if created_target and target is None:
                target = self.engine(name)
            try:
                if created_target:
                    with target.begin() as connection:
                        connection.execute(text(f"CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (created_at timestamptz NOT NULL, archive_sha256 varchar(64) NOT NULL)"))
                        if inspect(connection).has_table("auth_sessions"):
                            connection.execute(text("DELETE FROM auth_sessions"))
            except Exception:
                pass
            raise BackupError("restore_failed_target_requires_review", database=name if created_target else None) from None
        finally:
            if target is not None:
                target.dispose()
            admin.dispose()


def prune_backups(directory, *, retention_days=7, now=None):
    if not 1 <= retention_days <= 30:
        raise BackupError("backup_retention_must_be_1_to_30_days")
    folder = private_directory(directory)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    removed = 0
    for manifest in sorted(folder.glob("praxioj_*.json"))[:1000]:
        try:
            with open_private(manifest, "rb") as handle:
                metadata = json.loads(handle.read(8193))
            timestamp = datetime.fromisoformat(metadata["created_at"])
            if metadata["format"] != FORMAT or timestamp.tzinfo is None or timestamp >= cutoff:
                continue
            archive = folder / metadata["archive"]
            if archive.name != manifest.with_suffix(".dump").name or archive.parent != folder:
                raise BackupError("invalid_backup_manifest")
            digest, size = digest_file(archive)
            if digest != metadata["sha256"] or size != metadata["size_bytes"]:
                raise BackupError("backup_integrity_failed")
            archive.unlink()
            manifest.unlink()
            removed += 1
        except (OSError, ValueError, KeyError, TypeError):
            raise BackupError("backup_prune_failed") from None
    return removed


def main():
    parser = argparse.ArgumentParser(description="Local trusted PostgreSQL backup and quarantined restore verification")
    parser.add_argument("command", choices=["backup", "verify", "restore-test", "prune"])
    parser.add_argument("path", help="Private backup directory or trusted archive outside the repository")
    parser.add_argument("--container", help="Use PostgreSQL tools in this existing local database container")
    parser.add_argument("--retention-days", type=int, default=7)
    args = parser.parse_args()
    try:
        if args.command == "prune":
            result = {"removed_backups": prune_backups(args.path, retention_days=args.retention_days)}
        else:
            backend = PostgresBackup(os.environ.get("DATABASE_URL", ""), container=args.container)
            result = getattr(backend, args.command.replace("-", "_"))(args.path)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "failed", "code": error.code if isinstance(error, BackupError) else "backup_operation_failed",
                          "database": error.database if isinstance(error, BackupError) else None}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

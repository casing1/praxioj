"""Only random disposable databases and synthetic records are backed up/restored."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from praxioj_api.backup import (BackupError, PostgresBackup, assert_not_restored_database,
    digest_file, open_private, private_directory, prune_backups)

ROOT = Path(__file__).resolve().parents[2]


def test_backup_files_reject_repository_and_unsafe_access(tmp_path):
    with pytest.raises(BackupError, match="outside_repository"):
        private_directory(ROOT / "artifacts" / "backups")
    folder = private_directory(tmp_path / "private")
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    path = folder / "sample.dump"
    with open_private(path, "wb") as handle:
        handle.write(b"synthetic")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        open_private(path, "wb")
    path.chmod(0o644)
    with pytest.raises(BackupError, match="owner_only"):
        digest_file(path)
    path.chmod(0o600)
    link = folder / "link.dump"
    link.symlink_to(path)
    with pytest.raises(OSError):
        open_private(link, "rb")


def test_backup_checksum_failure_stops_before_postgres_tool(tmp_path, monkeypatch):
    backend = PostgresBackup("postgresql+psycopg://synthetic:synthetic@127.0.0.1:5432/synthetic")
    folder = private_directory(tmp_path / "private")
    archive = folder / "praxioj_synthetic.dump"
    with open_private(archive, "wb") as handle:
        handle.write(b"changed")
    with open_private(archive.with_suffix(".json"), "wb") as handle:
        handle.write(json.dumps({"format": "praxioj-postgres-backup/1", "archive": archive.name,
            "sha256": "0" * 64, "size_bytes": 7}).encode())
    monkeypatch.setattr(backend, "run", lambda *_a, **_k: pytest.fail("Corrupt archive reached PostgreSQL"))
    with pytest.raises(BackupError, match="integrity_failed"):
        backend.restore_test(archive)


def test_backup_prune_is_bounded_and_does_not_follow_manifest_paths(tmp_path):
    folder = private_directory(tmp_path / "private")
    archive = folder / "praxioj_old.dump"
    with open_private(archive, "wb") as handle:
        handle.write(b"synthetic")
    digest, size = digest_file(archive)
    metadata = {"format": "praxioj-postgres-backup/1", "archive": archive.name, "sha256": digest,
                "size_bytes": size, "created_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()}
    with open_private(archive.with_suffix(".json"), "wb") as handle:
        handle.write(json.dumps(metadata).encode())
    assert prune_backups(folder) == 1
    assert prune_backups(folder) == 0
    with pytest.raises(BackupError, match="1_to_30"):
        prune_backups(folder, retention_days=31)
    with open_private(folder / "praxioj_traversal.json", "wb") as handle:
        handle.write(json.dumps({**metadata, "archive": "../unrelated.dump"}).encode())
    with pytest.raises(BackupError, match="invalid_backup_manifest"):
        prune_backups(folder)


def test_backup_connection_scope_is_local_and_has_no_shell():
    for url in ("sqlite:///:memory:", "postgresql+psycopg://synthetic@remote.example/db",
                "postgresql+psycopg://synthetic@localhost/db?options=-csearch_path=other"):
        with pytest.raises(BackupError):
            PostgresBackup(url)
    with pytest.raises(BackupError):
        PostgresBackup("postgresql+psycopg://synthetic@localhost/db", container="--privileged")


def test_backup_cli_never_prints_raw_database_failures(monkeypatch, capsys):
    from praxioj_api import backup
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://synthetic:synthetic@localhost/db")
    monkeypatch.setattr("sys.argv", ["backup", "backup", "/unused"])
    def fail(*_args):
        raise RuntimeError("synthetic-private-connection-parameters")
    monkeypatch.setattr(backup.PostgresBackup, "backup", fail)
    with pytest.raises(SystemExit) as result:
        backup.main()
    assert result.value.code == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "backup_operation_failed"
    assert "synthetic-private" not in output.out + output.err


def test_misrouted_postgres_tools_fail_before_creating_restore_database(monkeypatch):
    from praxioj_api.backup import IDENTITY_SQL
    backend = PostgresBackup("postgresql+psycopg://synthetic:synthetic@localhost/synthetic", container="synthetic-container")
    statements = []
    class NativeConnection:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def execute(self, statement):
            statements.append(str(statement))
            assert str(statement) == IDENTITY_SQL, "Mismatched cluster reached a database mutation"
            return self
        def scalar_one(self):
            return {"cluster_id": "100", "database": "synthetic", "role": "synthetic"}
    class NativeEngine:
        def connect(self): return NativeConnection()
        def dispose(self): pass
    def engine(database=None, **kwargs):
        assert database is None and not kwargs, "Mismatched cluster reached CREATE DATABASE setup"
        return NativeEngine()
    monkeypatch.setattr(backend, "engine", engine)
    monkeypatch.setattr(backend, "verify", lambda _archive: {"sha256": "a" * 64})
    monkeypatch.setattr(backend, "run", lambda *_args, **_kwargs: json.dumps({
        "cluster_id": "200", "database": "synthetic", "role": "synthetic"}).encode())
    with pytest.raises(BackupError, match="cluster_identity_mismatch"):
        backend.restore_test("/synthetic-trusted-archive.dump")
    assert statements == [IDENTITY_SQL]


@pytest.mark.postgres
def test_real_postgres_backup_restore_preserves_synthetic_data_and_quarantines(tmp_path, monkeypatch):
    url = os.getenv("PRAXIOJ_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    container = os.getenv("PRAXIOJ_TEST_BACKUP_CONTAINER")
    if not url:
        pytest.skip("PostgreSQL URL required for real backup/restore verification")
    if not container and not all(shutil.which(program) for program in ("psql", "pg_dump", "pg_restore")):
        pytest.skip("PostgreSQL clients or PRAXIOJ_TEST_BACKUP_CONTAINER required")
    source = "praxioj_backup_test_" + uuid4().hex
    parsed = make_url(url).set(query={})
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    target_name = None
    failed_target = None
    collision_name = None
    source_engine = None
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{source}" TEMPLATE template0'))
    try:
        source_url = parsed.set(database=source).render_as_string(hide_password=False)
        monkeypatch.setenv("DATABASE_URL", source_url)
        command.upgrade(Config(str(ROOT / "apps/api/alembic.ini")), "head")
        source_engine = create_engine(source_url)
        from praxioj_api.database import session_factory
        from praxioj_api.models import AuthSession, SolveSession, User, utcnow
        from praxioj_api.registry import register_directory
        with session_factory(source_engine).begin() as db:
            version = register_directory(db, ROOT / "examples/problems/release-plan")
            user = User(username="backup_synthetic", identity_token_hash="a" * 64, password_hash="synthetic-unused-hash", is_active=True)
            db.add(user); db.flush()
            db.add(AuthSession(user_id=user.id, token_hash="b" * 64, csrf_hash="c" * 64,
                               expires_at=utcnow() + timedelta(hours=1)))
            db.add(SolveSession(user_id=user.id, problem_version_id=version.id, model_configuration={}, draft="synthetic backup canary"))
        backend = PostgresBackup(source_url, container=container)
        bounded = backend.engine()
        try:
            with bounded.connect() as connection:
                assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "2min"
                assert connection.execute(text("SHOW lock_timeout")).scalar_one() == "5s"
        finally:
            bounded.dispose()
        receipt = backend.backup(tmp_path / "private")
        archive = Path(receipt["archive"])
        assert backend.verify(archive)["sha256"] == receipt["sha256"]
        try:
            restored = backend.restore_test(archive)
        except BackupError as error:
            failed_target = error.database
            raise
        target_name = restored["database"]
        assert target_name != source and restored["status"] == "quarantined"
        assert restored["restored_counts"]["users"] == 1
        assert restored["restored_counts"]["solve_sessions"] == 1
        assert restored["revoked_auth_sessions"] == 1
        target = backend.engine(target_name)
        try:
            with target.connect() as connection:
                assert connection.execute(text("SELECT draft FROM solve_sessions")).scalar_one() == "synthetic backup canary"
                assert connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one() == 0
            with pytest.raises(RuntimeError, match="quarantined"):
                assert_not_restored_database(target)
            from fastapi.testclient import TestClient
            from praxioj_api.main import create_app
            from praxioj_api.settings import Settings
            from praxioj_api.jobs import JobRepository
            restored_url = parsed.set(database=target_name).render_as_string(hide_password=False)
            with pytest.raises(RuntimeError, match="quarantined"):
                with TestClient(create_app(Settings(database_url=restored_url, environment="test"))):
                    pytest.fail("Quarantined database started serving")
            with pytest.raises(RuntimeError, match="quarantined"):
                JobRepository(session_factory(target)).claim("synthetic-restore-worker")
        finally:
            target.dispose()
        with source_engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one() == 1
        backend.expected_revision = "unsupported_schema"
        with pytest.raises(BackupError, match="restore_failed_target_requires_review") as failure:
            backend.restore_test(archive)
        failed_target = failure.value.database
        assert failed_target and failed_target not in {source, target_name}
        failed_engine = backend.engine(failed_target)
        try:
            with pytest.raises(RuntimeError, match="quarantined"):
                assert_not_restored_database(failed_engine)
        finally:
            failed_engine.dispose()
        # Even a generated-name collision must not modify an existing database.
        collision_hex = uuid4().hex
        collision_name = "praxioj_restore_" + collision_hex
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{collision_name}" TEMPLATE template0'))
        collision = backend.engine(collision_name)
        try:
            with collision.begin() as connection:
                connection.execute(text("CREATE TABLE synthetic_sentinel (id integer)"))
            from praxioj_api import backup
            with monkeypatch.context() as scoped:
                scoped.setattr(backup, "uuid4", lambda: SimpleNamespace(hex=collision_hex))
                with pytest.raises(BackupError) as collision_error:
                    backend.restore_test(archive)
                assert collision_error.value.database is None
            assert set(inspect(collision).get_table_names()) == {"synthetic_sentinel"}
        finally:
            collision.dispose()
        with open(archive, "ab") as handle:
            handle.write(b"corruption")
        with pytest.raises(BackupError, match="integrity_failed"):
            backend.verify(archive)
    finally:
        if source_engine is not None:
            source_engine.dispose()
        with admin.connect() as connection:
            # Only these newly-created random synthetic databases are removed.
            for name in (target_name, failed_target, collision_name, source):
                if name:
                    connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()

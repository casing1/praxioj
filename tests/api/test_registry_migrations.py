from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from praxioj.problems import ProblemManifest, load_problem_package
from praxioj_api.database import make_engine
from praxioj_api.models import Base, ProblemVersion, TraceEvent
from praxioj_api.registry import VersionConflict, register_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_registration_is_idempotent_and_versions_are_immutable(app, client, session):
    original = load_problem_package(ROOT / "examples/problems/release-plan")
    with app.state.session_factory.begin() as db:
        first = register_manifest(db, original)
        second = register_manifest(db, original)
        assert first.id == second.id
        changed = original.model_dump(mode="json")
        changed["title"] = "Changed contents"
        with pytest.raises(VersionConflict):
            register_manifest(db, ProblemManifest.model_validate(changed))
        changed["version"] = "1.1.0"
        register_manifest(db, ProblemManifest.model_validate(changed))
    assert client.get("/api/problems").json()[0]["version"] == "1.1.0"
    assert client.get("/api/problems/release-plan").json()["title"] == "Changed contents"
    assert client.get("/api/problems/release-plan?version=1.0.0").json()["title"] == original.title
    assert client.get(f"/api/sessions/{session['id']}").json()["problem_version"] == "1.0.0"
    with app.state.session_factory() as db:
        assert len(db.scalars(select(ProblemVersion)).all()) == 2


def test_migration_schema_matches_orm_and_can_downgrade(database_url):
    engine = make_engine(database_url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    engine.dispose()


def test_database_prevents_duplicate_trace_sequences(app, session):
    with pytest.raises(IntegrityError):
        with app.state.session_factory.begin() as db:
            existing = db.scalar(select(TraceEvent).where(TraceEvent.session_id == session["id"]))
            db.add(TraceEvent(event_id=str(uuid4()), session_id=existing.session_id,
                              sequence_number=existing.sequence_number, event_type=existing.event_type,
                              timestamp=existing.timestamp, envelope=existing.envelope))


def test_database_prevents_duplicate_event_ids(app, session):
    with app.state.session_factory() as db:
        event = db.scalar(select(TraceEvent).where(TraceEvent.session_id == session["id"]))
        values = {"event_id": event.event_id, "session_id": event.session_id, "sequence_number": 2,
                  "event_type": event.event_type, "timestamp": event.timestamp, "envelope": event.envelope}
    with pytest.raises(IntegrityError):
        with app.state.session_factory.begin() as db:
            db.add(TraceEvent(**values))


def test_populated_m1_migration_preserves_sessions_messages_traces_and_usage(database_url):
    """Upgrade a genuine M1 schema with participant data, without recreating it."""
    import json
    from datetime import datetime, timezone
    from hashlib import sha256
    from sqlalchemy import text
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.downgrade(config, "0001_initial")
    engine = make_engine(database_url)
    manifest = load_problem_package(ROOT / "examples/problems/release-plan").model_dump(mode="json")
    owner, version, sid, mid, eid = [str(uuid4()) for _ in range(5)]
    now = datetime.now(timezone.utc)
    envelope = {"event_id": eid, "session_id": sid, "sequence_number": 1, "event_type": "ASSISTANT_MESSAGE",
                "timestamp": now.isoformat(), "schema_version": "1.0", "source": "server", "actor": "assistant",
                "resource_ids": {"message_id": mid}, "payload": {"content": "Old response", "usage": {
                    "input_tokens": 7, "output_tokens": 4, "estimated": True}}}
    with engine.begin() as db:
        db.execute(text("INSERT INTO users (id,identity_token_hash,role,created_at) VALUES (:id,:hash,'participant',:time)"),
                   {"id": owner, "hash": sha256(b"migration-identity").hexdigest(), "time": now})
        db.execute(text("INSERT INTO problems (id,created_at) VALUES ('release-plan',:time)"), {"time": now})
        db.execute(text("INSERT INTO problem_versions (id,problem_id,version,manifest_sha256,manifest,created_at) VALUES (:id,'release-plan','1.0.0',:hash,:manifest,:time)"),
                   {"id": version, "hash": "a" * 64, "manifest": json.dumps(manifest), "time": now})
        db.execute(text("INSERT INTO solve_sessions (id,user_id,problem_version_id,status,next_sequence_number,user_message_count,model_configuration,created_at) VALUES (:id,:user,:version,'active',2,1,:model,:time)"),
                   {"id": sid, "user": owner, "version": version, "model": json.dumps({"provider": "mock", "model": "praxioj-mock-v1", "temperature": 0, "max_output_tokens": 512}), "time": now})
        db.execute(text("INSERT INTO conversation_messages (id,session_id,position,role,content,created_at) VALUES (:id,:sid,1,'assistant','Old response',:time)"),
                   {"id": mid, "sid": sid, "time": now})
        db.execute(text("INSERT INTO trace_events (event_id,session_id,sequence_number,event_type,timestamp,envelope) VALUES (:id,:sid,1,'ASSISTANT_MESSAGE',:time,:envelope)"),
                   {"id": eid, "sid": sid, "time": now, "envelope": json.dumps(envelope)})
    command.upgrade(config, "head")
    from sqlalchemy.orm import Session
    from praxioj_api.models import ConversationMessage, ProviderCall, SolveSession
    with Session(engine) as db:
        session = db.get(SolveSession, sid)
        assert session.runtime_profile == "mock" and session.draft == "" and session.active_run_id is None
        assert session.next_sequence_number == 2 and session.user_message_count == 1
        assert db.get(ConversationMessage, mid).content == "Old response"
        assert db.get(TraceEvent, eid).envelope == envelope
        usage = db.scalar(select(ProviderCall).where(ProviderCall.session_id == sid))
        assert usage.input_tokens == 7 and usage.output_tokens == 4 and usage.estimated
    engine.dispose()

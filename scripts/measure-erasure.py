"""Synthetic SQLite SQL-count measurement; never opens an application database."""
import json
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from praxioj_api.models import Base, User, Problem, ProblemVersion, SolveSession, TraceEvent, uid, utcnow
from praxioj_api import job_models, retention_models, quota_models  # noqa: F401 — complete ORM metadata
from praxioj_api.retention import erase_account


def measure(count):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory.begin() as db:
        user = User(identity_token_hash=uid())
        db.add(user); db.flush(); user_id = user.id
        problem = Problem(id="synthetic")
        db.add(problem); db.flush()
        version = ProblemVersion(problem_id=problem.id, version="1.0.0", manifest_sha256="0" * 64, manifest={})
        db.add(version); db.flush()
        for _ in range(count):
            session = SolveSession(user_id=user_id, problem_version_id=version.id, model_configuration={})
            db.add(session); db.flush()
            db.add(TraceEvent(event_id=uid(), session_id=session.id, sequence_number=1,
                             event_type="TEST", timestamp=utcnow(), envelope={}))
    queries = []
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        queries.append(statement.split()[0])
    event.listen(engine, "before_cursor_execute", capture)
    with factory.begin() as db:
        erase_account(db, db.get(User, user_id))
    engine.dispose()
    return {"sessions": count, "sql_executions": len(queries)}


if __name__ == "__main__":
    print(json.dumps({"metric": "SQL executions, synthetic in-memory SQLite; not production latency",
                      "results": [measure(count) for count in (1, 10, 50)]}, indent=2))

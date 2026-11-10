"""Bounded, restartable maintenance independent of live AI workers."""
import json
import logging
from datetime import timedelta
from sqlalchemy import delete, or_, select
from .models import AuthRateLimit, AuthSession
from .quota_models import WorkerRecord
from .quotas import cleanup_quota_records
from .jobs import JobRepository, database_now
from .retention import audit, purge_expired

logger = logging.getLogger("praxioj.internal.operations")


def run_maintenance(factory, settings, *, limit=100):
    from .backup import assert_not_restored_database
    with factory() as db:
        assert_not_restored_database(db.connection())
    limit = min(max(limit, 1), 1000)
    recovered = JobRepository(factory, lease_seconds=settings.worker_lease_seconds,
        max_running=settings.worker_max_running).recover(limit)
    from .judge import JudgeBroker
    recovered_judge = JudgeBroker(factory, settings).recover(limit)
    purged = purge_expired(factory, settings, limit=limit)
    with factory.begin() as db:
        now = database_now(db)
        counts = cleanup_quota_records(db, now, limit)
        for model, key, condition, order in (
            (AuthRateLimit, AuthRateLimit.key_hash, AuthRateLimit.window_start < now - timedelta(days=1), AuthRateLimit.window_start),
            (AuthSession, AuthSession.id, or_(AuthSession.expires_at <= now, AuthSession.revoked_at.is_not(None)), AuthSession.expires_at),
            (WorkerRecord, WorkerRecord.id, WorkerRecord.heartbeat_at < now - timedelta(days=7), WorkerRecord.heartbeat_at)):
            ids = list(db.scalars(select(key).where(condition).order_by(order, key).limit(limit).with_for_update(skip_locked=True)))
            if ids:
                db.execute(delete(model).where(key.in_(ids)))
            counts[model.__tablename__] = len(ids)
        result = {"recovered_jobs": recovered, "recovered_judge_jobs": recovered_judge,
            "purged_trace_sessions": purged, **counts}
        audit(db, "maintenance_completed", **result)
    logger.info(json.dumps({"event": "maintenance_completed", **result}, separators=(",", ":")))
    return result


def main():
    from .database import make_engine, session_factory
    from .settings import Settings
    from .backup import assert_not_restored_database
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        assert_not_restored_database(engine)
        print(json.dumps(run_maintenance(session_factory(engine), settings)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

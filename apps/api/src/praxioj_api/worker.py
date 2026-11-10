"""Explicit worker process: ``python -m praxioj_api.worker``.

The API persists work but never launches this scheduler. PostgreSQL is required
outside the isolated test environment. A stopped worker does not retry a call.
"""
import argparse
import asyncio
from contextlib import suppress
import logging
import signal
from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from praxioj.runtime import AIRuntime, MockProvider
from .database import make_engine, session_factory
from .jobs import JobRepository
from .runs import RunManager
from .settings import Settings
from .operations import WorkerRegistry

logger = logging.getLogger("praxioj.internal.worker")


class Worker:
    def __init__(self, app, *, worker_id=None):
        self.app = app
        self.worker_id = worker_id or str(uuid4())
        if not 1 <= len(self.worker_id) <= 64:
            raise ValueError("Worker identifier must be between 1 and 64 characters")
        self.repository = JobRepository(app.state.session_factory, lease_seconds=app.state.settings.worker_lease_seconds,
            max_running=app.state.settings.worker_max_running)
        self.registry = WorkerRegistry(app.state.session_factory, self.worker_id)
        self._last_registry = None
        self.stop = asyncio.Event()
        self._last_retention = None

    async def _heartbeat(self, lease, execution):
        while not execution.done():
            await asyncio.sleep(self.app.state.settings.worker_heartbeat_seconds)
            try:
                alive = await asyncio.to_thread(self.repository.heartbeat, lease)
                await asyncio.to_thread(self.registry.touch, "DRAINING" if self.stop.is_set() else "BUSY", lease.run_id)
            except Exception:
                # Connection/SQL text may contain credentials; log only a safe code.
                logger.warning("worker_failure code=heartbeat_unavailable run_id=%s", lease.run_id)
                alive = False
            if not alive:
                execution.cancel()
                return

    async def run_once(self):
        from .backup import assert_not_restored_database
        await asyncio.to_thread(assert_not_restored_database, self.app.state.engine)
        if self.stop.is_set():
            return False
        # Each transaction is short; provider waits never retain a connection.
        if self._last_retention is None or monotonic() - self._last_retention >= 60:
            from .maintenance import run_maintenance
            results = await asyncio.to_thread(run_maintenance, self.app.state.session_factory, self.app.state.settings)
            recovered = results["recovered_jobs"]
            self._last_retention = monotonic()
        else:
            recovered = await asyncio.to_thread(self.repository.recover)
        if recovered or self._last_registry is None or monotonic() - self._last_registry >= self.app.state.settings.worker_heartbeat_seconds:
            await asyncio.to_thread(self.registry.touch, "IDLE", recovered=recovered)
            self._last_registry = monotonic()
        if self.stop.is_set():
            return False
        lease = await asyncio.to_thread(self.repository.claim, self.worker_id)
        if lease is None:
            return False
        await asyncio.to_thread(self.registry.touch, "BUSY", lease.run_id)
        executor = RunManager(self.app, lease)
        execution = asyncio.create_task(executor.execute(lease.run_id))
        heartbeat = asyncio.create_task(self._heartbeat(lease, execution))
        stopping = asyncio.create_task(self.stop.wait())
        try:
            done, _ = await asyncio.wait({execution, stopping}, return_when=asyncio.FIRST_COMPLETED)
            if stopping in done and not execution.done():
                await asyncio.to_thread(self.registry.touch, "DRAINING", lease.run_id)
                # Continue heartbeats during a bounded drain. No new job is claimed.
                try:
                    await asyncio.wait_for(asyncio.shield(execution), self.app.state.settings.worker_shutdown_seconds)
                except TimeoutError:
                    execution.cancel()
            await execution
        except asyncio.CancelledError:
            execution.cancel()
            with suppress(asyncio.CancelledError):
                await execution
            raise
        except Exception:
            # A persistence outage leaves the lease for another worker to reconcile.
            logger.error("worker_failure code=state_persistence_failed run_id=%s", lease.run_id)
        finally:
            heartbeat.cancel()
            stopping.cancel()
            await asyncio.gather(heartbeat, stopping, return_exceptions=True)
        await asyncio.to_thread(self.registry.touch, "STOPPED" if self.stop.is_set() else "IDLE", lease.run_id, finished=True)
        await asyncio.to_thread(self.repository.recover)
        return True

    async def serve(self):
        try:
            while not self.stop.is_set():
                try:
                    worked = await self.run_once()
                except Exception:
                    logger.error("worker_failure code=queue_unavailable")
                    worked = False
                if not worked:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(self.stop.wait(), timeout=self.app.state.settings.worker_poll_seconds)
        finally:
            try:
                await asyncio.to_thread(self.registry.touch, "STOPPED")
            except Exception:
                logger.error("worker_failure code=registry_unavailable")


async def run_worker(settings, *, once=False):
    engine = make_engine(settings.database_url)
    app = SimpleNamespace(state=SimpleNamespace(settings=settings, engine=engine,
        session_factory=session_factory(engine), runtime=AIRuntime(MockProvider())))
    from .backup import assert_not_restored_database
    assert_not_restored_database(engine)
    worker = Worker(app)
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(name, worker.stop.set)
    try:
        if once:
            await worker.run_once()
            await asyncio.to_thread(worker.registry.touch, "STOPPED")
        else:
            await worker.serve()
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="PraxiOJ durable AI worker")
    parser.add_argument("--once", action="store_true", help="Reconcile expired jobs and process at most one pending job")
    args = parser.parse_args()
    asyncio.run(run_worker(Settings(), once=args.once))


if __name__ == "__main__":
    main()

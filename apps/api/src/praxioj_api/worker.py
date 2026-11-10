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

logger = logging.getLogger("praxioj.internal.worker")


class Worker:
    def __init__(self, app, *, worker_id=None):
        self.app = app
        self.worker_id = worker_id or str(uuid4())
        if not 1 <= len(self.worker_id) <= 64:
            raise ValueError("Worker identifier must be between 1 and 64 characters")
        self.repository = JobRepository(app.state.session_factory, lease_seconds=app.state.settings.worker_lease_seconds)
        self.stop = asyncio.Event()
        self._last_retention = None

    async def _heartbeat(self, lease, execution):
        while not execution.done():
            await asyncio.sleep(self.app.state.settings.worker_heartbeat_seconds)
            try:
                alive = await asyncio.to_thread(self.repository.heartbeat, lease)
            except Exception:
                # Connection/SQL text may contain credentials; log only a safe code.
                logger.warning("worker_failure code=heartbeat_unavailable run_id=%s", lease.run_id)
                alive = False
            if not alive:
                execution.cancel()
                return

    async def run_once(self):
        # Each transaction is short; provider waits never retain a connection.
        await asyncio.to_thread(self.repository.recover)
        if self._last_retention is None or monotonic() - self._last_retention >= 60:
            from .retention import purge_expired
            await asyncio.to_thread(purge_expired, self.app.state.session_factory, self.app.state.settings)
            self._last_retention = monotonic()
        lease = await asyncio.to_thread(self.repository.claim, self.worker_id)
        if lease is None:
            return False
        executor = RunManager(self.app, lease)
        execution = asyncio.create_task(executor.execute(lease.run_id))
        heartbeat = asyncio.create_task(self._heartbeat(lease, execution))
        stopping = asyncio.create_task(self.stop.wait())
        try:
            done, _ = await asyncio.wait({execution, stopping}, return_when=asyncio.FIRST_COMPLETED)
            if stopping in done and not execution.done():
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
        await asyncio.to_thread(self.repository.recover)
        return True

    async def serve(self):
        while not self.stop.is_set():
            try:
                worked = await self.run_once()
            except Exception:
                logger.error("worker_failure code=queue_unavailable")
                worked = False
            if not worked:
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.stop.wait(), timeout=self.app.state.settings.worker_poll_seconds)


async def run_worker(settings, *, once=False):
    engine = make_engine(settings.database_url)
    app = SimpleNamespace(state=SimpleNamespace(settings=settings, engine=engine,
        session_factory=session_factory(engine), runtime=AIRuntime(MockProvider())))
    worker = Worker(app)
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(name, worker.stop.set)
    try:
        if once:
            await worker.run_once()
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

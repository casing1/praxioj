"""Explicit worker harness for API regressions; never enabled by application settings."""
import asyncio
from contextlib import contextmanager
import threading

from praxioj_api.worker import Worker


@contextmanager
def worker_thread(app):
    ready = threading.Event()
    state = {}

    def run():
        async def serve():
            worker = Worker(app)
            state.update(worker=worker, loop=asyncio.get_running_loop())
            ready.set()
            await worker.serve()
        asyncio.run(serve())

    thread = threading.Thread(target=run, name="praxioj-test-worker", daemon=True)
    thread.start()
    assert ready.wait(5), "Test worker did not initialize"
    try:
        yield state["worker"]
    finally:
        state["loop"].call_soon_threadsafe(state["worker"].stop.set)
        thread.join(10)
        assert not thread.is_alive(), "Test worker did not stop"

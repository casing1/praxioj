"""Real PostgreSQL timeout and native server proxy-boundary checks."""
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from praxioj_api.database import make_engine


@pytest.mark.postgres
def test_database_deadlines_preserve_isolated_schema_and_bound_row_wait(database_url):
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL required for server deadlines and row locks")
    engine = make_engine(database_url)
    try:
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT current_schema()" )).startswith("praxioj_test_")
            assert connection.scalar(text("SHOW statement_timeout")) == "10s"
            assert connection.scalar(text("SHOW lock_timeout")) == "5s"
            connection.execute(text("CREATE TABLE timeout_probe (id integer PRIMARY KEY, value integer NOT NULL)"))
            connection.execute(text("INSERT INTO timeout_probe VALUES (1, 0)"))
        with engine.begin() as owner:
            owner.execute(text("SELECT * FROM timeout_probe WHERE id = 1 FOR UPDATE"))
            started = time.monotonic()
            with pytest.raises(OperationalError) as failure:
                with engine.begin() as waiter:
                    waiter.execute(text("UPDATE timeout_probe SET value = 1 WHERE id = 1"))
            assert failure.value.orig.sqlstate == "55P03"
            assert 4 <= time.monotonic() - started < 12
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM timeout_probe")) == 0
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_real_native_server_ignores_forged_forwarded_addresses(database_url):
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL required for independent native API process")
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    env = {**os.environ, "DATABASE_URL": database_url, "PRAXIOJ_ENV": "test", "PRAXIOJ_API_IP_LIMIT": "2",
           "PRAXIOJ_API_RATE_WINDOW_SECONDS": "60", "PRAXIOJ_DEFAULT_PROFILE": "mock",
           "PRAXIOJ_LLM_BASE_URL": "", "PRAXIOJ_LLM_MODEL": "", "PRAXIOJ_LLM_API_KEY": ""}
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "praxioj_api.main:app", "--host", "127.0.0.1",
                                "--port", str(port), "--no-proxy-headers", "--no-access-log"],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=2) as browser:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                assert process.poll() is None, "Native test server stopped before readiness"
                try:
                    if browser.get("/api/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.05)
            else:
                pytest.fail("Native test server did not become ready")
            responses = [browser.get("/api/problems", headers={"X-Forwarded-For": f"203.0.113.{number}",
                "Forwarded": f"for=203.0.113.{number}"}) for number in range(1, 4)]
            assert [response.status_code for response in responses] == [200, 200, 429]
            assert int(responses[-1].headers["Retry-After"]) > 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

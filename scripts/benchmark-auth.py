#!/usr/bin/env python3
"""Measure synthetic invalid-login latency and SQL counts in a temporary SQLite DB.

Run from the repository root with the project's Python environment. This is a
repeatable local comparison workload, not a production load test or timing proof.
No network provider is configured and no credentials, cookies or hashes are printed.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import tempfile
import time

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event

from praxioj_api.main import create_app
from praxioj_api.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args()
    if not 3 <= args.samples <= 30:
        parser.error("Use 3–30 samples to stay within this bounded fixture's rate budget")
    password = "synthetic-benchmark-passphrase-only"
    previous_url = os.environ.get("DATABASE_URL")
    try:
        with tempfile.TemporaryDirectory(prefix="praxioj-auth-benchmark-") as directory:
            url = "sqlite:///" + str(Path(directory) / "benchmark.db")
            os.environ["DATABASE_URL"] = url
            command.upgrade(Config("apps/api/alembic.ini"), "head")
            app = create_app(Settings(database_url=url, environment="test", auth_account_limit=100,
                auth_ip_limit=100, default_profile="mock", llm_base_url=None, llm_model=None, llm_api_key=None))
            count = [0]
            event.listen(app.state.engine, "before_cursor_execute", lambda *_: count.__setitem__(0, count[0] + 1))
            rows = {}
            try:
                with TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as client:
                    registered = client.post("/api/auth/register", json={"username": "baseline_user", "password": password})
                    # Allows this identical workload to compare the M3 and M4 contracts.
                    assert registered.status_code in {201, 202}, "Synthetic account setup failed"
                    for label, username in (("existing_invalid", "baseline_user"), ("missing_invalid", "missing_user")):
                        times, queries = [], []
                        for _ in range(args.samples):
                            count[0] = 0
                            start = time.perf_counter()
                            response = client.post("/api/auth/login", json={"username": username, "password": password + "wrong"})
                            times.append((time.perf_counter() - start) * 1000)
                            queries.append(count[0])
                            assert response.status_code == 401, "Invalid-login fixture was not rejected"
                        rows[label] = {"samples": args.samples, "median_ms": round(statistics.median(times), 2),
                            "min_ms": round(min(times), 2), "max_ms": round(max(times), 2), "sql_counts": queries}
            finally:
                app.state.engine.dispose()
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
        "backend": "SQLite temp database; ASGI TestClient; Argon2id64MiB/t3/p4", "results": rows}, indent=2))


if __name__ == "__main__":
    main()

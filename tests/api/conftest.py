"""Every API test uses the real migration and database-backed application.

Set PRAXIOJ_TEST_DATABASE_URL to PostgreSQL to run the same suite there. Each test
gets a disposable schema, so existing application tables are never truncated.
"""
from pathlib import Path
from uuid import uuid4
import os

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from praxioj_api.main import create_app
from praxioj_api.registry import register_directory
from praxioj_api.settings import Settings
from worker_support import worker_thread

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def database_url(tmp_path, monkeypatch):
    postgres_url = os.getenv("PRAXIOJ_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    engine = None
    schema = None
    if postgres_url:
        if not postgres_url.startswith("postgresql+psycopg://"):
            raise ValueError("PRAXIOJ_TEST_DATABASE_URL must use postgresql+psycopg")
        schema = f"praxioj_test_{uuid4().hex}"
        engine = create_engine(postgres_url)
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(postgres_url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    command.upgrade(config, "head")
    yield url
    if engine is not None:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
def app(database_url):
    application = create_app(Settings(database_url=database_url, environment="test"))
    with application.state.session_factory.begin() as db:
        register_directory(db, ROOT / "examples/problems/release-plan")
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app):
    with worker_thread(app), TestClient(app, base_url="http://localhost:8000", headers={"Origin": "http://localhost:8000"}) as instance:
        authenticate_client(instance)
        yield instance


def authenticate_client(client, username=None):
    """Use real registration and CSRF validation, never an authentication bypass."""
    response = client.post("/api/auth/register", json={
        "username": username or "participant_" + uuid4().hex[:16],
        "password": "synthetic-test-passphrase-2026",
    }, headers={"Origin": "http://localhost:8000"})
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


@pytest.fixture
def session(client):
    response = client.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"})
    assert response.status_code == 201, response.text
    return response.json()

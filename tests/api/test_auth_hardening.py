"""M4 account lifecycle, bounded confirmation, and enumeration boundary checks."""
from datetime import timedelta
from dataclasses import replace
from hashlib import sha256
import json
import os

from fastapi import Request
import pytest
from sqlalchemy import select

from conftest import authenticate_client
from test_auth import PASSWORD, raw_client
from praxioj_api.models import AuthRateLimit, AuthSession, User, utcnow
from praxioj_api.retention_models import AuditRecord
from praxioj_api.security import require_recent_reauthentication
from praxioj_api.auth import consume_rate_bucket


def test_registration_does_not_enumerate_or_replace_accounts(app):
    with raw_client(app) as browser:
        body = {"username": "private_account", "password": PASSWORD}
        first = browser.post("/api/auth/register", json=body)
        duplicate = browser.post("/api/auth/register", json={**body, "password": PASSWORD + "different"})
        assert first.status_code == duplicate.status_code == 202
        assert first.json() == duplicate.json() and set(first.json()) == {"message"}
        assert not first.headers.get_list("set-cookie") and not duplicate.headers.get_list("set-cookie")
        assert browser.get("/api/auth/me").status_code == 401
        bad = browser.post("/api/auth/login", json={**body, "password": PASSWORD + "different"})
        missing = browser.post("/api/auth/login", json={"username": "missing_account", "password": PASSWORD})
        assert bad.status_code == missing.status_code == 401 and bad.json() == missing.json()
        assert browser.post("/api/auth/login", json=body).status_code == 200
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(User).where(User.username == "private_account")))) == 1


def test_login_never_adopts_a_caller_supplied_session(app):
    with raw_client(app) as browser:
        chosen = "synthetic-attacker-chosen-session"
        browser.cookies.set("praxioj_session", chosen, domain="localhost.local", path="/")
        authenticate_client(browser, "fixation_subject")
        actual = browser.cookies["praxioj_session"]
        assert actual != chosen
        with app.state.session_factory() as db:
            assert db.scalar(select(AuthSession).where(AuthSession.token_hash == sha256(chosen.encode()).hexdigest())) is None
        with raw_client(app) as attacker:
            attacker.cookies.set("praxioj_session", chosen)
            assert attacker.get("/api/auth/me").status_code == 401


def test_own_session_list_and_revocation_never_exposes_other_accounts(app):
    with raw_client(app) as first, raw_client(app) as second, raw_client(app) as outsider:
        authenticate_client(first, "session_owner")
        response = second.post("/api/auth/login", json={"username": "session_owner", "password": PASSWORD})
        second.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        authenticate_client(outsider, "another_owner")
        sessions = first.get("/api/auth/sessions").json()
        assert len(sessions) == 2 and sum(item["current"] for item in sessions) == 1
        assert all(set(item) == {"id", "created_at", "expires_at", "current"} for item in sessions)
        current = next(item for item in sessions if item["current"])
        other = next(item for item in sessions if not item["current"])
        assert outsider.post(f"/api/auth/sessions/{other['id']}/revoke", json={}).status_code == 404
        assert first.post(f"/api/auth/sessions/{other['id']}/revoke", json={}).status_code == 204
        assert second.get("/api/auth/me").status_code == 401
        # Repeating a previously completed revocation is safe for the owner.
        assert first.post(f"/api/auth/sessions/{other['id']}/revoke", json={}).status_code == 204
        assert first.post(f"/api/auth/sessions/{current['id']}/revoke", json={}).status_code == 204
        assert not first.cookies and first.get("/api/auth/me").status_code == 401


def test_password_change_requires_old_password_and_revokes_every_session(app):
    with raw_client(app) as first, raw_client(app) as second:
        authenticate_client(first, "password_owner")
        login = second.post("/api/auth/login", json={"username": "password_owner", "password": PASSWORD})
        second.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        wrong = first.post("/api/auth/password", json={"current_password": PASSWORD + "wrong", "new_password": PASSWORD + "new"})
        assert wrong.status_code == 403 and first.get("/api/auth/me").status_code == 200
        changed = first.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD + "new"})
        assert changed.status_code == 204 and not first.cookies
        assert second.get("/api/auth/me").status_code == 401
        assert second.post("/api/auth/login", json={"username": "password_owner", "password": PASSWORD}).status_code == 401
        assert second.post("/api/auth/login", json={"username": "password_owner", "password": PASSWORD + "new"}).status_code == 200
        with app.state.session_factory() as db:
            assert len(list(db.scalars(select(AuthSession).where(AuthSession.revoked_at.is_(None))))) == 1


def test_confirmation_requires_csrf_is_session_scoped_and_expires(app):
    @app.post("/test/confirmed-operation")
    def confirmed(request: Request):
        with app.state.session_factory.begin() as db:
            user = require_recent_reauthentication(db, request)
            return {"id": user.id}

    with raw_client(app) as first, raw_client(app) as second:
        identity = authenticate_client(first, "confirmation_owner")
        response = second.post("/api/auth/login", json={"username": "confirmation_owner", "password": PASSWORD})
        second.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert first.get("/api/auth/me").json()["reauthenticated_until"] is None
        assert first.post("/test/confirmed-operation", json={}).status_code == 403
        assert first.post("/api/auth/reauthenticate", json={"password": PASSWORD}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
        assert first.post("/api/auth/reauthenticate", json={"password": PASSWORD + "wrong"}).status_code == 403
        confirmed = first.post("/api/auth/reauthenticate", json={"password": PASSWORD})
        assert confirmed.status_code == 200 and set(confirmed.json()) == {"expires_at"}
        assert first.post("/test/confirmed-operation", json={}).json() == {"id": identity["user"]["id"]}
        assert second.post("/test/confirmed-operation", json={}).status_code == 403
        with app.state.session_factory.begin() as db:
            login = db.scalar(select(AuthSession).where(AuthSession.token_hash == sha256(first.cookies["praxioj_session"].encode()).hexdigest()))
            login.reauthenticated_at = utcnow() - timedelta(seconds=app.state.settings.auth_reauthentication_seconds + 1)
        assert first.post("/test/confirmed-operation", json={}).status_code == 403


def test_confirmation_failure_budget_commits_and_audit_is_bounded(app):
    with raw_client(app) as browser:
        identity = authenticate_client(browser, "confirmation_limited")
        app.state.settings = replace(app.state.settings, auth_account_limit=2)
        for _ in range(2):
            assert browser.post("/api/auth/reauthenticate", json={"password": PASSWORD + "wrong"}).status_code == 403
        for _ in range(3):
            response = browser.post("/api/auth/reauthenticate", json={"password": PASSWORD})
            assert response.status_code == 429
            assert response.headers["RateLimit-Remaining"] == "0"
            assert 1 <= int(response.headers["Retry-After"]) <= 300
        with app.state.session_factory() as db:
            rows = list(db.scalars(select(AuditRecord)))
            assert len([row for row in rows if row.action == "auth_throttled"]) == 1
            serialized = json.dumps([{"action": row.action, "actor": row.actor_id, "details": row.details} for row in rows])
            assert PASSWORD not in serialized and identity["user"]["username"] not in serialized
            assert browser.cookies["praxioj_session"] not in serialized
            assert all(row.reauthenticated_at is None for row in db.scalars(select(AuthSession)))
            # Recovery after a short fixed window does not permanently lock the account.
            for row in db.scalars(select(AuthRateLimit)):
                row.window_start = utcnow() - timedelta(seconds=301)
            db.commit()
        assert browser.post("/api/auth/reauthenticate", json={"password": PASSWORD}).status_code == 200


def test_configured_session_cap_and_sensitive_validation(app):
    app.state.settings = replace(app.state.settings, auth_max_sessions=1)
    with raw_client(app) as first, raw_client(app) as second:
        authenticate_client(first, "one_session")
        response = second.post("/api/auth/login", json={"username": "one_session", "password": PASSWORD})
        second.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert first.get("/api/auth/me").status_code == 401
        assert len(second.get("/api/auth/sessions").json()) == 1
        response = second.post("/api/auth/password", json={"current_password": "short", "new_password": PASSWORD})
        assert response.status_code == 422 and PASSWORD not in response.text and '"short"' not in response.text


def test_api_admission_persists_rejections_and_ignores_forwarded_peers(app):
    from praxioj_api.main import create_app
    limited = create_app(replace(app.state.settings, api_ip_limit=2))
    try:
        with raw_client(limited) as browser:
            for index in range(2):
                response = browser.get("/not-found", headers={"X-Forwarded-For": f"192.0.2.{index}"})
                assert response.status_code == 404
            response = browser.get("/api/problems", headers={"X-Forwarded-For": "192.0.2.200"})
            assert response.status_code == 429 and response.headers["RateLimit-Remaining"] == "0"
            assert 1 <= int(response.headers["Retry-After"]) <= 60
            # Health bypass is only a liveness exception, not a resource API.
            assert browser.get("/api/health").status_code != 429
        with raw_client(limited) as another:
            assert another.get("/api/problems").status_code == 429
    finally:
        limited.state.engine.dispose()


def test_api_admission_database_failure_omits_private_details(app, monkeypatch, caplog):
    from types import SimpleNamespace
    from sqlalchemy.exc import OperationalError
    def broken():
        raise OperationalError("private connection string", {}, RuntimeError("private credential"))
    monkeypatch.setattr(app.state, "session_factory", SimpleNamespace(begin=broken))
    with raw_client(app) as browser:
        response = browser.get("/api/problems")
        assert response.status_code == 503 and response.headers["Retry-After"] == "1"
        assert "private" not in response.text and "private" not in caplog.text
        assert "rate_store_unavailable" in caplog.text


def test_atomic_rate_window_boundary_resets_and_denials_saturate(app):
    now = utcnow()
    key = sha256(b"synthetic-fixed-window").hexdigest()
    with app.state.session_factory.begin() as db:
        first = consume_rate_bucket(db, key, 2, 60, now)
        assert first.allowed and first.remaining == 1 and first.reset_seconds == 60
    with app.state.session_factory.begin() as db:
        assert consume_rate_bucket(db, key, 2, 60, now + timedelta(seconds=59)).allowed
        denied = consume_rate_bucket(db, key, 2, 60, now + timedelta(seconds=59))
        assert not denied.allowed and denied.first_denial and denied.reset_seconds == 1
        for _ in range(20):
            repeated = consume_rate_bucket(db, key, 2, 60, now + timedelta(seconds=59))
            assert not repeated.allowed and not repeated.first_denial
    with app.state.session_factory.begin() as db:
        assert db.get(AuthRateLimit, key).count == 4
        renewed = consume_rate_bucket(db, key, 2, 60, now + timedelta(seconds=60))
        assert renewed.allowed and renewed.remaining == 1 and renewed.reset_seconds == 60


@pytest.mark.postgres
@pytest.mark.skipif(not (os.getenv("PRAXIOJ_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")), reason="PostgreSQL required for concurrent API admission")
def test_api_admission_budget_is_shared_across_api_instances(app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from praxioj_api.main import create_app
    applications = [create_app(replace(app.state.settings, api_ip_limit=2)) for _ in range(4)]
    gate = Barrier(4)
    def get(application):
        with raw_client(application) as browser:
            gate.wait(timeout=10)
            return browser.get("/api/problems").status_code
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            assert sorted(executor.map(get, applications)) == [200, 200, 429, 429]
    finally:
        for application in applications:
            application.state.engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not (os.getenv("PRAXIOJ_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")), reason="PostgreSQL required for simultaneous password changes")
def test_concurrent_password_changes_revoke_stale_authority(app):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    first, second = raw_client(app), raw_client(app)
    try:
        authenticate_client(first, "racing_password")
        login = second.post("/api/auth/login", json={"username": "racing_password", "password": PASSWORD})
        second.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        gate = Barrier(2)
        def change(pair):
            browser, suffix = pair
            gate.wait(timeout=10)
            return browser.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD + suffix}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(change, [(first, "first"), (second, "second")]))
        assert statuses.count(204) == 1 and all(status in {204, 401} for status in statuses)
        assert first.get("/api/auth/me").status_code == second.get("/api/auth/me").status_code == 401
        with app.state.session_factory() as db:
            assert not list(db.scalars(select(AuthSession).where(AuthSession.revoked_at.is_(None))))
            assert len(list(db.scalars(select(AuditRecord).where(AuditRecord.action == "auth_password_changed")))) == 1
    finally:
        first.close()
        second.close()

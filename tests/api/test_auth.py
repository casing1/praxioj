"""Real Argon2id, cookie, CSRF, role and account-boundary integration tests."""
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from praxioj_api.auth import verify_password
from praxioj_api.models import AuthRateLimit, AuthSession, ProblemVersion, User, utcnow
from conftest import authenticate_client

ORIGIN = {"Origin": "http://localhost:8000"}
PASSWORD = "synthetic-test-passphrase-2026"


def raw_client(app):
    return TestClient(app, base_url="http://localhost:8000", headers=ORIGIN)


def test_account_registration_hashes_credentials_and_session(app):
    with raw_client(app) as browser:
        result = authenticate_client(browser, "alice")
        assert result["user"]["role"] == "participant"
        me = browser.get("/api/auth/me")
        assert me.status_code == 200 and me.json() == result
        token = browser.cookies["praxioj_session"]
        csrf = result["csrf_token"]
        with app.state.session_factory() as db:
            user = db.get(User, result["user"]["id"])
            assert user.password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
            assert verify_password(user.password_hash, PASSWORD)
            assert not verify_password(user.password_hash, PASSWORD + "wrong")
            login = db.scalar(select(AuthSession))
            assert login.token_hash == sha256(token.encode()).hexdigest()
            assert login.csrf_hash == sha256(csrf.encode()).hexdigest()
            assert token not in repr(login.__dict__) and csrf not in repr(login.__dict__)
        assert "password" not in me.text and "token_hash" not in me.text


def test_login_rotation_logout_and_expiry(app):
    with raw_client(app) as browser:
        authenticate_client(browser, "alice")
        old = browser.cookies["praxioj_session"]
        failed = browser.post("/api/auth/login", json={"username": "alice", "password": PASSWORD + "wrong"})
        assert failed.status_code == 401
        result = browser.post("/api/auth/login", json={"username": "ALICE", "password": PASSWORD})
        assert result.status_code == 200
        assert browser.cookies["praxioj_session"] != old
        browser.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        with raw_client(app) as stale:
            stale.cookies.set("praxioj_session", old)
            assert stale.get("/api/auth/me").status_code == 401
        assert browser.post("/api/auth/logout", json={}).status_code == 204
        assert browser.get("/api/auth/me").status_code == 401
        assert not browser.cookies
        result = browser.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
        browser.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        with app.state.session_factory.begin() as db:
            login = db.scalar(select(AuthSession).where(AuthSession.token_hash == sha256(browser.cookies["praxioj_session"].encode()).hexdigest()))
            login.expires_at = utcnow() - timedelta(seconds=1)
        assert browser.get("/api/auth/me").status_code == 401
        assert browser.post("/api/sessions", json={"problem_id": "release-plan", "version": "1.0.0"}).status_code == 401


def test_cookie_flags_and_csrf_origin_boundaries(app):
    with raw_client(app) as browser:
        response = browser.post("/api/auth/register", json={"username": "alice", "password": PASSWORD})
        assert response.status_code == 202 and not response.headers.get_list("set-cookie")
        response = browser.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
        cookie_headers = response.headers.get_list("set-cookie")
        assert len(cookie_headers) == 2
        for cookie in cookie_headers:
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=28800" in cookie
            assert "Domain=" not in cookie
        body = {"problem_id": "release-plan", "version": "1.0.0"}
        assert browser.post("/api/sessions", json=body).status_code == 403
        browser.headers["X-CSRF-Token"] = "forged"
        assert browser.post("/api/sessions", json=body).status_code == 403
        browser.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert browser.post("/api/sessions", json=body).status_code == 201
        assert browser.post("/api/sessions", json=body, headers={"Origin": "https://evil.invalid"}).status_code == 403
        browser.headers.pop("Origin")
        assert browser.post("/api/auth/login", json={"username": "alice", "password": PASSWORD}).status_code == 403
        browser.headers["Origin"] = "http://localhost:8000"
        assert browser.post("/api/auth/login", json={"username": "alice", "password": PASSWORD}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_invalid_credentials_never_echo_password(app):
    with raw_client(app) as browser:
        response = browser.post("/api/auth/register", json={"username": "x", "password": "secret"})
        assert response.status_code == 422 and '"secret"' not in response.text
        assert "input" not in response.text
        response = browser.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "role": "administrator"})
        assert response.status_code == 422 and PASSWORD not in response.text


def test_old_development_identity_cannot_authenticate_or_claim_account(app):
    token = "synthetic-old-browser-token"
    with app.state.session_factory.begin() as db:
        user = User(identity_token_hash=sha256(token.encode()).hexdigest(), role="administrator")
        db.add(user)
        db.flush()
        old_id = user.id
    with raw_client(app) as browser:
        browser.cookies.set("praxioj_dev_identity", token)
        browser.cookies.set("praxioj_session", token)
        assert browser.get("/api/auth/me").status_code == 401
        result = authenticate_client(browser, "new_account")
        assert result["user"]["id"] != old_id and result["user"]["role"] == "participant"
    with app.state.session_factory() as db:
        old = db.get(User, old_id)
        assert not old.is_active and old.username is None and old.password_hash is None


def test_rate_limit_persists_across_clients_and_ignores_forwarded_headers(app):
    with raw_client(app) as browser:
        authenticate_client(browser, "alice")
        for index in range(8):
            response = browser.post("/api/auth/login", json={"username": "alice", "password": PASSWORD + "bad"},
                                    headers={"X-Forwarded-For": f"10.0.0.{index}"})
            assert response.status_code == 401
    with raw_client(app) as another:
        response = another.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
        assert response.status_code == 429 and "Retry-After" in response.headers
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(AuthRateLimit)))) == 3  # API peer, auth peer, auth account.
        assert all("alice" not in key for key in db.scalars(select(AuthRateLimit.key_hash)))


def test_participant_cannot_call_role_apis_or_read_other_account(app, client, session):
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/api/author/problems").status_code == 403
    with app.state.session_factory() as db:
        manifest = db.scalar(select(ProblemVersion)).manifest
    assert client.post("/api/author/problems", json={"manifest": manifest}).status_code == 403
    with raw_client(app) as other:
        authenticate_client(other, "other_user")
        sid = session["id"]
        for path in (f"/api/sessions/{sid}", f"/api/sessions/{sid}/trace", f"/api/sessions/{sid}/files", f"/api/sessions/{sid}/usage", f"/api/sessions/{sid}/runs"):
            assert other.get(path).status_code == 404
        assert other.put(f"/api/sessions/{sid}/draft", json={"content": "steal"}).status_code == 404
        assert other.post(f"/api/sessions/{sid}/runs", json={"content": "steal", "request_id": str(uuid4())}).status_code == 404
        assert other.post(f"/api/sessions/{sid}/submissions", json={"content": "steal"}).status_code == 404


def test_author_owns_immutable_versions_and_admin_can_manage(app):
    with app.state.session_factory() as db:
        manifest = dict(db.scalar(select(ProblemVersion)).manifest)
    manifest["id"] = "authored-problem"
    with raw_client(app) as author, raw_client(app) as other:
        first = authenticate_client(author, "author_one")
        second = authenticate_client(other, "author_two")
        with app.state.session_factory.begin() as db:
            db.get(User, first["user"]["id"]).role = "author"
            db.get(User, second["user"]["id"]).role = "author"
        created = author.post("/api/author/problems", json={"manifest": manifest})
        assert created.status_code == 201, created.text
        assert author.post("/api/author/problems", json={"manifest": manifest}).status_code == 201
        assert other.post("/api/author/problems", json={"manifest": manifest}).status_code == 404
        assert len(author.get("/api/author/problems").json()) == 1
        assert other.get("/api/author/problems").json() == []
        changed = {**manifest, "title": "Changed immutable version"}
        assert author.post("/api/author/problems", json={"manifest": changed}).status_code == 409
        with app.state.session_factory.begin() as db:
            db.get(User, second["user"]["id"]).role = "administrator"
        assert other.get("/api/admin/users").status_code == 200
        assert "password_hash" not in other.get("/api/admin/users").text
        assert other.post("/api/author/problems", json={"manifest": {**manifest, "version": "1.0.1"}}).status_code == 201
        # Unowned operator manifests cannot be adopted by ordinary authors.
        manifest["id"] = "release-plan"
        assert author.post("/api/author/problems", json={"manifest": manifest}).status_code == 404


def test_secure_cookie_mode_accepts_https_loopback_and_rejects_http_cookie_use(database_url):
    from praxioj_api.main import create_app
    from praxioj_api.settings import Settings
    application = create_app(Settings(database_url=database_url, environment="test", cookie_secure=True))
    with TestClient(application, base_url="https://localhost:8000", headers={"Origin": "https://localhost:8000"}) as browser:
        response = browser.post("/api/auth/register", json={"username": "secure_user", "password": PASSWORD})
        assert response.status_code == 202, response.text
        response = browser.post("/api/auth/login", json={"username": "secure_user", "password": PASSWORD})
        assert response.status_code == 200, response.text
        assert all("Secure" in value and "HttpOnly" in value for value in response.headers.get_list("set-cookie"))
        browser.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert browser.get("/api/auth/me").status_code == 200
        assert browser.get("http://localhost:8000/api/auth/me").status_code == 401
        assert browser.post("/api/auth/logout", json={}).status_code == 204
    application.state.engine.dispose()


def test_active_session_cap_revokes_oldest_without_storing_raw_tokens(app):
    browsers = []
    try:
        first = raw_client(app)
        browsers.append(first)
        authenticate_client(first, "multiple_sessions")
        for _ in range(5):
            browser = raw_client(app)
            browsers.append(browser)
            response = browser.post("/api/auth/login", json={"username": "multiple_sessions", "password": PASSWORD})
            assert response.status_code == 200
        assert browsers[0].get("/api/auth/me").status_code == 401
        assert all(browser.get("/api/auth/me").status_code == 200 for browser in browsers[1:])
        with app.state.session_factory() as db:
            assert len(list(db.scalars(select(AuthSession).where(AuthSession.revoked_at.is_(None))))) == 5
    finally:
        for browser in browsers:
            browser.close()


def test_operator_role_change_revokes_sessions_and_rejects_legacy_accounts(app, client, monkeypatch, capsys):
    from praxioj_api.cli import main
    user = client.get("/api/auth/me").json()["user"]
    monkeypatch.setenv("PRAXIOJ_ENV", "test")
    monkeypatch.setattr("sys.argv", ["praxioj", "set-role", user["username"], "author"])
    main()
    assert '"sessions_revoked": true' in capsys.readouterr().out
    from praxioj_api.retention_models import AuditRecord
    with app.state.session_factory() as db:
        record = db.scalar(select(AuditRecord).where(AuditRecord.action == "role_changed"))
        assert record.resource_id == user["id"] and record.details["role"] == "author"
    assert client.get("/api/auth/me").status_code == 401
    response = client.post("/api/auth/login", json={"username": user["username"], "password": PASSWORD})
    assert response.status_code == 200 and response.json()["user"]["role"] == "author"
    monkeypatch.setattr("sys.argv", ["praxioj", "set-role", "unknown_legacy", "administrator"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


@pytest.mark.postgres
@pytest.mark.skipif(not (os.getenv("PRAXIOJ_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")), reason="PostgreSQL required for concurrent authentication rate limits")
def test_concurrent_failed_logins_share_one_persistent_rate_budget(app):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Barrier
    app.state.settings = replace(app.state.settings, auth_account_limit=4)
    with raw_client(app) as browser:
        authenticate_client(browser, "limited_account")
    gate = Barrier(4)
    def attempt(_):
        browser = raw_client(app)
        try:
            gate.wait(timeout=10)
            return browser.post("/api/auth/login", json={"username": "limited_account", "password": PASSWORD + "bad"}).status_code
        finally:
            browser.close()
    with ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(executor.map(attempt, range(4)))
    assert sorted(statuses) == [401, 401, 429, 429]

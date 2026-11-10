#!/usr/bin/env python3
"""Loopback-only synthetic Judge flow; role bootstrap is a trusted operator action."""
import argparse
import http.cookiejar
import json
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, body=None, *, status=200, timeout=40):
        headers = {"Accept": "application/json", "Origin": self.base}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(self.base + "/api" + path, data=data, headers=headers)
        try:
            response = self.opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.status == status, f"Unexpected HTTP {response.status} for {path}"
            raw = response.read()
            return json.loads(raw) if raw else None

    def login(self, credentials):
        auth = self.request("/auth/login", credentials)
        self.csrf = auth["csrf_token"]
        return auth


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-container", default="praxioj-api-1", help="Local API container for existing role CLI")
    parser.add_argument("--expect-unavailable", action="store_true")
    parser.add_argument("--restart-api", action="store_true", help="Verify a pending synthetic job survives API restart")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
        parser.error("Use a loopback HTTP URL without credentials")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args.api_container):
        parser.error("Use a local API container name or ID")
    client = Client(base)
    credentials = {"username": "m5_smoke_" + uuid4().hex[:20], "password": "synthetic-" + secrets.token_urlsafe(24)}
    client.request("/auth/register", credentials, status=202)
    # Operator bootstrap is outside the Mock backend. No shell or submitted code runs.
    subprocess.run(["docker", "exec", args.api_container, "python", "-m", "praxioj_api.cli", "set-role",
        credentials["username"], "administrator"], check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert client.login(credentials)["user"]["role"] == "administrator"
    runtime = client.request("/internal/judge/runtime")
    assert runtime["independent_execution_evidence"] is False
    fixture = runtime["fixture"]
    session = client.request("/sessions", {"problem_id": fixture["problem_id"], "version": fixture["version"], "runtime_profile": "mock"}, status=201)
    receipt = client.request(f"/sessions/{session['id']}/submissions", {"content": fixture["submission_content"]}, status=201)
    original = client.request(f"/evaluations/{receipt['evaluation_id']}")
    before = client.request(f"/sessions/{session['id']}/trace/integrity")
    assert before["status"] == "verified"
    body = {"submission_id": receipt["submission_id"], "request_id": str(uuid4()), "fixture_id": fixture["id"]}
    if args.expect_unavailable:
        assert runtime["availability"]["status"] == "unavailable"
        client.request("/internal/judge/jobs", body, status=503)
    else:
        assert runtime["availability"]["status"] == "available"
        pending = client.request("/internal/judge/jobs", body, status=202)
        assert client.request("/internal/judge/jobs", body, status=202)["id"] == pending["id"]
        if args.restart_api:
            # Trusted integration driver only; this never runs in the Mock backend.
            subprocess.run(["docker", "restart", args.api_container], check=True, timeout=20,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 20
            while True:
                try:
                    client.request("/health", timeout=2)
                    break
                except (OSError, AssertionError):
                    if time.monotonic() >= deadline:
                        raise AssertionError("Synthetic API did not become ready") from None
                    time.sleep(.2)
            assert client.request(f"/internal/judge/jobs/{pending['id']}")["state"] == "PENDING"
        completed = client.request(f"/internal/judge/jobs/{pending['id']}/dispatch", {})
        assert completed["state"] == "COMPLETED" and completed["provenance"] == "synthetic_mock"
        assert completed["assessment"]["independent_execution_evidence"] is False
        assert completed["assessment"]["evaluation"]["score"] == 100
        client.request(f"/internal/judge/jobs/{pending['id']}/dispatch", {}, status=409)
        cancelled = client.request("/internal/judge/jobs", {**body, "request_id": str(uuid4())}, status=202)
        assert client.request(f"/internal/judge/jobs/{cancelled['id']}/cancel", {})["state"] == "CANCELLED"
        client.request(f"/internal/judge/jobs/{cancelled['id']}/dispatch", {}, status=409)
        client.request("/internal/judge/jobs", {**body, "source": "not an accepted authority field"}, status=422)
        assert client.request(f"/evaluations/{receipt['evaluation_id']}") == original
        assert client.request(f"/sessions/{session['id']}/trace/integrity") == before
        client.request("/auth/reauthenticate", {"password": credentials["password"]})
        exported = client.request("/auth/export", {})
        assert len(exported["judge_executions"]) == 2
        serialized = json.dumps(exported)
        assert all(name not in serialized for name in ("capability_hash", "worker_id", "request_template"))
    client.request("/auth/reauthenticate", {"password": credentials["password"]})
    assert client.request("/auth/delete", {})["deleted_sessions"] == 1
    client.request("/auth/me", status=401)
    print(json.dumps({"status": "passed", "mode": "default_unavailable" if args.expect_unavailable else "synthetic_mock",
        "original_evaluation_preserved": True, "independent_execution_evidence": False,
        "idempotence_replay_cancel": "not_applicable" if args.expect_unavailable else "verified",
        "pending_job_after_api_restart": bool(args.restart_api and not args.expect_unavailable),
        "trace": "unchanged_verified", "synthetic_account_erased": True}, indent=2))


if __name__ == "__main__":
    main()

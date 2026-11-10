#!/usr/bin/env python3
"""Local M4 smoke: only create/export/erase synthetic accounts owned by this run."""
import argparse
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, None
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, body=None, method=None, status=200):
        headers = {"Accept": "application/json", "Origin": self.base}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(self.base + "/api" + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            assert response.status == status, f"Unexpected status {response.status} for {path}"
            raw = response.read()
            return json.loads(raw) if raw else None

    def login(self, credentials):
        account = self.request("/auth/login", credentials)
        assert account["user"]["username"] == credentials["username"]
        self.csrf = account["csrf_token"]
        return account


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
        parser.error("Use a localhost HTTP URL without credentials")
    client = Client(base)
    credentials = {"username": "m4_smoke_" + uuid4().hex[:16], "password": "synthetic-" + uuid4().hex}
    client.request("/auth/register", credentials, status=202)
    account = client.login(credentials)
    client.request("/admin/operations", status=403)
    client.request("/auth/export", {}, status=403)
    session = client.request("/sessions", {"problem_id": "evidence-plan", "version": "1.0.0", "runtime_profile": "mock"}, status=201)
    sid = session["id"]
    run = client.request(f"/sessions/{sid}/runs", {"content": "Please save a release plan in plan.txt", "request_id": str(uuid4())}, status=202)
    deadline = time.monotonic() + 30
    while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(.15)
        run = client.request(f"/runs/{run['id']}")
    assert run["status"] == "completed", "Synthetic run did not complete"
    files = client.request(f"/sessions/{sid}/files")
    plan = next(item for item in files if item["path"] == "plan.txt")
    client.request(f"/sessions/{sid}/draft", {"content": plan["content"]}, "PUT")
    assert client.request(f"/sessions/{sid}")["draft"] == plan["content"]
    receipt = client.request(f"/sessions/{sid}/submissions", {"content": plan["content"]}, status=201)
    evaluation = client.request(f"/evaluations/{receipt['evaluation_id']}")
    assert evaluation["score"] == 100 and len(evaluation["criteria"]) == 6
    assert client.request(f"/sessions/{sid}/trace/integrity")["status"] == "verified"
    usage = client.request("/account/usage")
    assert usage["daily"]["model_calls"] == 2 and usage["daily"]["tool_calls"] == 1
    assert usage["daily"]["uncertain_calls"] == 2 and usage["daily"]["reserved_policy_units"] > 0
    assert usage["daily"]["input_tokens"] == 0, "Mock estimates were incorrectly labelled exact"
    client.request("/auth/reauthenticate", {"password": credentials["password"]})
    exported = client.request("/auth/export", {})
    assert exported["profile"]["id"] == account["user"]["id"]
    assert [item["id"] for item in exported["sessions"]] == [sid]
    assert len(exported["evaluations"]) == 1 and exported["traces"]
    assert credentials["password"] not in json.dumps(exported)
    other_login = Client(base)
    other_login.login(credentials)
    signins = client.request("/auth/sessions")
    other_id = next(item["id"] for item in signins if not item["current"])
    client.request(f"/auth/sessions/{other_id}/revoke", {}, status=204)
    other_login.request("/auth/me", status=401)
    changed_password = "synthetic-new-" + uuid4().hex
    client.request("/auth/password", {"current_password": credentials["password"], "new_password": changed_password}, status=204)
    client.request("/auth/me", status=401)
    credentials["password"] = changed_password
    client.login(credentials)
    client.request("/auth/reauthenticate", {"password": changed_password})
    assert client.request("/auth/delete", {})["deleted_sessions"] == 1
    client.request("/auth/me", status=401)
    client.request("/auth/login", credentials, status=401)
    print(json.dumps({"status": "passed", "score": evaluation["score"], "criteria": 6,
        "trace": "verified", "model_calls": 2, "tool_calls": 1, "unknown_usage_preserved": True,
        "export": "owner_only", "session_revocation": "passed", "password_rotation": "passed",
        "synthetic_account_erased": True, "admin_access_denied": True}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Exercise the live local M2 API, tools, artifacts, usage, submission and trace.

Defaults to the offline mock profile. Creates one persisted demo session.
Selecting compatible uses the operator-configured endpoint; run that variant
against scripts/compatible-fixture.py for credential-free validation.
"""

import argparse
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--profile", choices=["mock", "compatible"], default="mock")
    parser.add_argument("--problem", choices=["workspace-plan", "evidence-plan"], default="workspace-plan")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use a local HTTP development URL")
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    csrf = None

    def request(path, body=None, method=None, opener=client):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers.update({"Content-Type": "application/json", "Origin": base})
            if csrf:
                headers["X-CSRF-Token"] = csrf
            data = json.dumps(body).encode()
        req = urllib.request.Request(base + "/api" + path, data=data, headers=headers, method=method)
        with opener.open(req, timeout=10) as response:
            return json.load(response)

    credentials = {"username": "smoke_" + uuid4().hex[:16], "password": "synthetic-" + uuid4().hex}
    request("/auth/register", credentials)
    account = request("/auth/login", credentials)
    csrf = account["csrf_token"]
    options = request("/runtime/options")
    assert args.profile in {item["id"] for item in options["profiles"]}, "Requested server profile not configured"
    session = request("/sessions", {"problem_id": args.problem, "version": "1.0.0", "runtime_profile": args.profile})
    sid = session["id"]
    body = {"content": "Please save a release plan in plan.txt using the permitted workspace tool.", "request_id": str(uuid4())}
    run = request(f"/sessions/{sid}/runs", body)
    assert request(f"/sessions/{sid}/runs", body)["id"] == run["id"], "Run retry was not idempotent"
    deadline = time.monotonic() + 30
    while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.1)
        run = request(f"/runs/{run['id']}")
    assert run["status"] == "completed", run
    assert run["job"]["state"] == "COMPLETED"
    files = request(f"/sessions/{sid}/files")
    plan = next(item for item in files if item["path"] == "plan.txt")
    assert plan["revision"] == 1, "Tool executed twice after request retry"
    draft = request(f"/sessions/{sid}/draft", {"content": plan["content"]}, "PUT")
    assert draft["content"] == plan["content"]
    resumed = request(f"/sessions/{sid}")
    assert resumed["draft"] == plan["content"]
    assert any(item["role"] == "tool" for item in resumed["messages"])
    usage = request(f"/sessions/{sid}/usage")
    assert usage["model_calls"] == 2 and usage["tool_calls"] == 1, usage
    assert usage["cost_estimate"] is None, "No prices configured in the default smoke environment"
    receipt = request(f"/sessions/{sid}/submissions", {"content": plan["content"]})
    result = request(f"/evaluations/{receipt['evaluation_id']}")
    assert result["status"] == "completed" and result["score"] == 100
    trace = request(f"/sessions/{sid}/trace")
    assert [e["sequence_number"] for e in trace] == list(range(1, len(trace) + 1))
    assert request(f"/sessions/{sid}/trace/integrity")["status"] == "verified"
    if args.problem == "evidence-plan":
        assert result["trace_integrity"]["status"] == "verified"
        assert len(result["criteria"]) == 6
    types = [e["event_type"] for e in trace]
    for event in ["PROVIDER_CALL_STARTED", "PROVIDER_CALL_COMPLETED", "TOOL_CALL_REQUESTED", "TOOL_CALL_AUTHORIZED", "TOOL_CALL_COMPLETED", "ARTIFACT_UPDATED", "SESSION_STATE_CHANGED", "EVALUATION_COMPLETED"]:
        assert event in types, event
    outsider = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    credentials = {"username": "outsider_" + uuid4().hex[:16], "password": "synthetic-" + uuid4().hex}
    request("/auth/register", credentials, opener=outsider)
    request("/auth/login", credentials, opener=outsider)
    for path in [f"/runs/{run['id']}", f"/sessions/{sid}/usage", f"/sessions/{sid}/files", f"/sessions/{sid}/trace"]:
        try:
            request(path, opener=outsider)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("Cross-browser private resource access succeeded")
    print(json.dumps({"status": "passed", "problem": args.problem, "profile": args.profile, "session_id": sid,
                      "run_status": run["status"], "model_calls": usage["model_calls"],
                      "tool_calls": usage["tool_calls"], "events": len(trace), "score": result["score"],
                      "usage_complete": usage["usage_complete"], "ownership_checks": 4}, indent=2))


if __name__ == "__main__":
    main()

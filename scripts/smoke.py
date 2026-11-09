#!/usr/bin/env python3
"""Exercise the real local HTTP workflow. Creates one persisted demo session."""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use a local HTTP development URL.")
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path: str, body: dict | None = None, *, opener=client):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers.update({"Content-Type": "application/json", "Origin": base})
            data = json.dumps(body).encode()
        req = urllib.request.Request(base + "/api" + path, data=data, headers=headers)
        with opener.open(req, timeout=15) as response:
            return json.load(response)

    health = request("/health")
    assert health["status"] == "ok" and health["provider"] == "mock"
    problems = request("/problems")
    assert isinstance(problems, list) and problems, "No registered problems"
    problem = next((item for item in problems if item["id"] == "release-plan" and item["version"] == "1.0.0"), None)
    assert problem is not None, "Register sample release-plan version 1.0.0 before this smoke check"
    detail = request(f'/problems/{problem["id"]}?version={problem["version"]}')
    assert all("config" not in criterion for criterion in detail["evaluation"]["criteria"])
    session = request("/sessions", {"problem_id": problem["id"], "version": problem["version"]})
    session_id = session["id"]
    messages = request(f"/sessions/{session_id}/messages", {"content": "Help me state the goal, verification steps, and risk for this release."})
    assert messages["assistant_message"]["content"], "No mock assistant response"
    assert request(f"/sessions/{session_id}")["messages"], "Conversation was not persisted"
    submitted = request(f"/sessions/{session_id}/submissions", {"content": "Goal: ship the small release. Verification: run tests and review results. Risk: prepare a rollback if validation fails."})
    result = request(f'/evaluations/{submitted["evaluation_id"]}')
    assert result["status"] == "completed", result
    assert result["score"] == result["maximum_score"] == 100, result
    assert result["submission_id"] == submitted["submission_id"]
    assert result["problem_version"] == problem["version"]
    trace = request(f"/sessions/{session_id}/trace")
    assert [event["sequence_number"] for event in trace] == list(range(1, len(trace) + 1))
    for event_type in ["SESSION_STARTED", "USER_MESSAGE", "ASSISTANT_MESSAGE", "ARTIFACT_UPDATED", "SUBMISSION_CREATED", "EVALUATION_COMPLETED", "SESSION_ENDED"]:
        assert event_type in [event["event_type"] for event in trace], event_type
    assert request(f"/sessions/{session_id}")["status"] == "submitted"

    outsider = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    for path in [f"/sessions/{session_id}", f"/sessions/{session_id}/trace", f'/evaluations/{submitted["evaluation_id"]}']:
        try:
            request(path, opener=outsider)
        except urllib.error.HTTPError as error:
            assert error.code == 404, f"Expected owner-scoped 404, got {error.code}"
        else:
            raise AssertionError("Another browser could read a private solve resource")
    print(json.dumps({"status": "passed", "health": health, "session_id": session_id, "evaluation_status": result["status"], "score": result["score"], "maximum_score": result["maximum_score"], "events": len(trace), "ownership_checks": 3}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only validation of actual GitHub PR metadata, not claims in its body.

Maintainer-authored PRs are enforced. External/bot PRs receive advisory findings
for maintainer triage without changing authorship, permissions or metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, ProxyHandler


TYPES = {"feat", "fix", "perf", "refactor", "test", "docs", "ci", "build", "chore"}
WORK_LABELS = {"enhancement", "bug", "documentation", "maintenance", "security", "testing", "performance"}
AREAS = {f"area:{name}" for name in ("framework", "api", "broker", "runner", "database", "frontend", "ci", "docs")}
ISSUE_REF = re.compile(r"\b(?:closes|fixes|resolves|refs)\s+#([1-9][0-9]*)\b", re.IGNORECASE)


def referenced_issues(body: str) -> list[int]:
    # Bound API reads even if a PR body is unusually large or repeats references.
    return sorted({int(match) for match in ISSUE_REF.findall(body)})


def validate(pr: dict, issues: dict[int, dict], maintainer: str = "casing1") -> list[str]:
    errors: list[str] = []
    title = pr.get("title", "")
    match = re.fullmatch(r"([a-z]+)\(([a-z0-9][a-z0-9-]*)\): ([^\n]+)", title)
    if not match or match[1] not in TYPES or not match[3].strip() or not title.isascii():
        errors.append("Use an English Conventional Commit title: <type>(<scope>): <summary>.")
    labels = {label["name"] for label in pr.get("labels", [])}
    if not labels & WORK_LABELS:
        errors.append("Apply an actual work-type label.")
    if not labels & AREAS:
        errors.append("Apply an actual area:* label.")
    if maintainer not in {assignee["login"] for assignee in pr.get("assignees", [])}:
        errors.append("Assign the maintainer for maintainer-led work; preserve other valid assignees.")
    milestone = pr.get("milestone")
    if not milestone:
        errors.append("Apply an actual GitHub milestone to the PR.")
    refs = referenced_issues(pr.get("body") or "")
    if not refs:
        errors.append("Link an issue using Closes #N or Refs #N.")
    if len(refs) > 20:
        errors.append("More than 20 linked issues requires an explicit manual metadata review.")
        refs = refs[:20]
    for number in refs:
        issue = issues.get(number)
        if issue is None or "pull_request" in issue:
            errors.append(f"Issue #{number} was not verified as a repository issue.")
            continue
        linked = issue.get("milestone")
        if not linked or not milestone or linked.get("number") != milestone.get("number"):
            errors.append(f"Issue #{number} and PR must have the same actual milestone.")
        issue_labels = {label["name"] for label in issue.get("labels", [])}
        if not issue_labels & WORK_LABELS or not issue_labels & AREAS:
            errors.append(f"Issue #{number} needs actual work-type and area:* labels.")
        assignees = {assignee["login"] for assignee in issue.get("assignees", [])}
        if not assignees or (issue.get("user", {}).get("login") == maintainer and maintainer not in assignees):
            errors.append(f"Issue #{number} needs its actual assignee; maintainer-authored work defaults to the maintainer.")
    return errors


def github_json(path: str) -> dict:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "PraxiOJ-governance-check"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # API origin/path are generated from validated repository/number arguments.
    # Disable inherited proxies; no user-supplied URL or response content is logged.
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(f"https://api.github.com/{path}", headers=headers), timeout=15) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("GitHub metadata response exceeds size limit")
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("GitHub metadata must be an object")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", help="owner/repository; reads GitHub with a read-only token if available")
    parser.add_argument("--number", type=int)
    parser.add_argument("--pr-json", type=Path, help="offline REST pull-request snapshot")
    parser.add_argument("--issues-json", type=Path, help="offline array of REST issue snapshots")
    parser.add_argument("--maintainer", default="casing1")
    args = parser.parse_args()
    lookup_errors: list[str] = []
    if args.pr_json:
        if not args.issues_json:
            parser.error("--pr-json requires --issues-json")
        pr = json.loads(args.pr_json.read_text(encoding="utf-8"))
        issues = {issue["number"]: issue for issue in json.loads(args.issues_json.read_text(encoding="utf-8"))}
    else:
        if not args.repository or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            parser.error("supply --repository owner/repository and --number, or offline snapshots")
        if args.number is None or args.number < 1:
            parser.error("--number must be positive")
        try:
            pr = github_json(f"repos/{args.repository}/pulls/{args.number}")
        except (HTTPError, URLError, OSError, ValueError):
            print("Unable to verify current GitHub metadata. No metadata was changed; retry or record a manual review.",
                  file=sys.stderr)
            return 1
        issues = {}
        for number in referenced_issues(pr.get("body") or "")[:20]:
            try:
                issues[number] = github_json(f"repos/{args.repository}/issues/{number}")
            except (HTTPError, URLError, OSError, ValueError):
                lookup_errors.append(f"Current metadata for issue #{number} could not be verified.")
    errors = validate(pr, issues, args.maintainer) + lookup_errors
    strict = pr.get("user", {}).get("login") == args.maintainer
    mode = "required maintainer check" if strict else "external/bot advisory; maintainer triage required"
    print(f"PR metadata: {mode}.")
    for error in errors:
        # Controlled diagnostics never echo untrusted titles, bodies or credentials.
        print(f"- {error}")
    if not errors:
        print("Title, labels, assignee, actual milestone and linked issue milestone verified.")
    return 1 if strict and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

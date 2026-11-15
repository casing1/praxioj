# SPDX-License-Identifier: Apache-2.0
"""Offline boundary checks for repository governance tooling."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def load_script(name: str):
    path = Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


docs = load_script("check-docs")
metadata = load_script("check-pr-metadata")


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_links_headings_code_examples_and_external_urls(tmp_path):
    write(tmp_path, "target.md", "# API `request_id`\n\n## Repeat\n\n## Repeat\n\n## 한국어 제목\n")
    source = write(tmp_path, "README.md", """# Documentation
[API](target.md#api-request_id)
[duplicate](target.md#repeat-1)
[Korean](target.md#한국어-제목)
[external](https://example.invalid/never-fetched)
`[inline example](missing.md)`
```markdown
[example](also-missing.md)
```
[reference][contract]
[contract]: target.md#repeat
""")
    assert docs.check_document(tmp_path, source) == []


def test_missing_path_fragment_and_escape_are_rejected(tmp_path):
    write(tmp_path, "target.md", "# Found\n")
    source = write(tmp_path, "README.md", "[a](missing.md)\n[b](target.md#absent)\n[c](../outside.md)\n")
    errors = docs.check_document(tmp_path, source)
    assert len(errors) == 3
    assert "missing local target" in errors[0]
    assert "missing heading fragment" in errors[1]
    assert "escapes repository" in errors[2]


def test_percent_encoded_paths_and_html_anchors(tmp_path):
    write(tmp_path, "some file.md", '# Title\n<a id="explicit"></a>\n')
    source = write(tmp_path, "README.md", "[a](some%20file.md#explicit)\n")
    assert docs.check_document(tmp_path, source) == []


def test_html_anchor_examples_in_code_do_not_satisfy_fragments(tmp_path):
    target = write(tmp_path, "target.md", """# Title
<a id="real"></a>
```html
<a id="ghost"></a>
```
`<a name="inline-ghost"></a>`
""")
    assert docs.anchors(target.read_text()) == {"title", "real"}
    source = write(tmp_path, "README.md", "[real](target.md#real)\n[ghost](target.md#ghost)\n")
    assert len(docs.check_document(tmp_path, source)) == 1


@pytest.mark.parametrize("headings,expected", [
    ("# Foo\n# Foo\n# Foo-1\n", {"foo", "foo-1", "foo-1-1"}),
    ("# Foo\n# Foo-1\n# Foo\n", {"foo", "foo-1", "foo-2"}),
])
def test_generated_heading_suffixes_do_not_collide(headings, expected):
    assert docs.anchors(headings) == expected


def test_translation_pairs_require_reciprocal_language_links(tmp_path):
    write(tmp_path, "README.md", "[한국어](ko/README.md)\n")
    write(tmp_path, "ko/README.md", "[English](../README.md)\n")
    manifest = write(tmp_path, "translations.json", json.dumps({"README.md": "ko/README.md"}))
    assert docs.check_translations(tmp_path, manifest) == []
    write(tmp_path, "ko/README.md", "# 한국어\n")
    assert docs.check_translations(tmp_path, manifest) == ["ko/README.md: missing reciprocal language link to README.md"]


def test_duplicate_translation_targets_and_escaping_manifest_rejected(tmp_path):
    manifest = write(tmp_path, "translations.json", json.dumps({"a.md": "ko.md", "b.md": "ko.md"}))
    with pytest.raises(ValueError, match="unique"):
        docs.check_translations(tmp_path, manifest)
    manifest.write_text(json.dumps({"../a.md": "ko.md"}))
    with pytest.raises(ValueError, match="within repository"):
        docs.check_translations(tmp_path, manifest)


def test_outside_source_and_manifest_symlinks_are_not_read(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = write(tmp_path, "private.md", "[private text](private-target)\n")
    source = root / "README.md"
    source.symlink_to(outside)
    assert docs.check_document(root, source) == ["README.md: Markdown source escapes repository"]
    manifest = root / "translations.json"
    manifest.symlink_to(outside)
    with pytest.raises(ValueError, match="within repository"):
        docs.check_translations(root, manifest)


def valid_pr():
    return {"title": "feat(judge): renew active execution leases", "body": "Closes #21\nRefs #22",
            "user": {"login": "casing1"}, "labels": [{"name": "enhancement"}, {"name": "area:broker"}],
            "assignees": [{"login": "casing1"}, {"login": "contributor"}], "milestone": {"number": 1}}


def valid_issue(number=21):
    return {"number": number, "user": {"login": "casing1"}, "milestone": {"number": 1},
            "labels": [{"name": "enhancement"}, {"name": "area:broker"}], "assignees": [{"login": "casing1"}]}


def test_metadata_checks_actual_objects_and_preserves_multiple_assignees():
    assert metadata.validate(valid_pr(), {21: valid_issue(), 22: valid_issue(22)}) == []


@pytest.mark.parametrize("title", ["M6 work", "update", "feat: missing scope", "unknown(api): something", "feat(api): 변경"])
def test_title_requires_allowed_conventional_type_scope_and_english(title):
    pr = valid_pr()
    pr["title"] = title
    assert any("Conventional" in error for error in metadata.validate(pr, {}))


def test_body_claims_do_not_replace_metadata():
    pr = valid_pr()
    pr.update(labels=[], assignees=[], milestone=None, body="Closes #21\nMilestone M6-A; labels: enhancement area:api")
    errors = metadata.validate(pr, {21: valid_issue()})
    assert len(errors) == 5
    assert any("actual work-type" in error for error in errors)
    assert any("same actual milestone" in error for error in errors)


def test_pr_reference_is_not_an_issue_and_wrong_milestone_rejected():
    issue = valid_issue(22)
    issue["milestone"] = {"number": 2}
    errors = metadata.validate(valid_pr(), {21: {"pull_request": {}, "milestone": {"number": 1}},
                                           22: issue})
    assert len(errors) == 2


def test_linked_issue_requires_actual_labels_and_assignee():
    issue = valid_issue()
    issue.update(labels=[], assignees=[])
    errors = metadata.validate(valid_pr(), {21: issue, 22: valid_issue(22)})
    assert len(errors) == 2
    assert any("Issue #21 needs actual work-type" in error for error in errors)
    assert any("Issue #21 needs its actual assignee" in error for error in errors)


def test_external_issue_existing_contributor_assignment_is_accepted():
    issue = valid_issue()
    issue.update(user={"login": "external-contributor"}, assignees=[{"login": "external-contributor"}])
    assert metadata.validate(valid_pr(), {21: issue, 22: valid_issue(22)}) == []


def test_reference_reads_are_deduplicated_and_bounded():
    assert metadata.referenced_issues("Closes #21\nRefs #21\nrefs #22") == [21, 22]
    pr = valid_pr()
    pr["body"] = "\n".join(f"Refs #{index}" for index in range(1, 22))
    assert any("20 linked issues" in error for error in metadata.validate(pr, {}))


@pytest.mark.parametrize("author,expected", [("casing1", 1), ("external-contributor", 0), ("dependabot[bot]", 0)])
def test_external_and_bot_metadata_is_advisory(tmp_path, monkeypatch, author, expected):
    pr = valid_pr()
    pr.update(user={"login": author}, labels=[])
    pr_file = write(tmp_path, "pr.json", json.dumps(pr))
    issues_file = write(tmp_path, "issues.json", json.dumps([valid_issue(), valid_issue(22)]))
    monkeypatch.setattr("sys.argv", ["check-pr-metadata", "--pr-json", str(pr_file), "--issues-json", str(issues_file)])
    assert metadata.main() == expected


@pytest.mark.parametrize("author,expected", [("casing1", 1), ("dependabot[bot]", 0)])
def test_missing_remote_issue_is_strict_only_for_maintainer(monkeypatch, author, expected):
    pr = valid_pr()
    pr["user"] = {"login": author}

    def fetch(path):
        if "/pulls/" in path:
            return pr
        raise OSError("synthetic lookup unavailable")

    monkeypatch.setattr(metadata, "github_json", fetch)
    monkeypatch.setattr("sys.argv", ["check-pr-metadata", "--repository", "casing1/praxioj", "--number", "1"])
    assert metadata.main() == expected

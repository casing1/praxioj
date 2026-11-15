#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check repository Markdown links and explicit translation pairs without network I/O.

This intentionally checks paths, heading fragments and reciprocal language links,
not prose quality or semantic translation equivalence. Code examples are ignored.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit


LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+['\"][^\n]*?['\"])?\s*\)")
REFERENCE = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", re.MULTILINE)


def prose(text: str) -> str:
    """Remove fenced code, retaining line positions and inline heading text."""
    result: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            result.append("\n" if line.endswith("\n") else "")
        elif marker:
            fence = marker[1]
            result.append("\n" if line.endswith("\n") else "")
        else:
            # Preserve inline code text in headings: GitHub includes it in anchors.
            result.append(line)
    return "".join(result)


def anchors(text: str) -> set[str]:
    rendered = prose(text)
    used: set[str] = set()
    # HTML-looking examples in fenced or inline code do not create rendered IDs.
    html = re.sub(r"(`+).*?\1", "", rendered)
    found = set(re.findall(r"<(?:a|\w+)\b[^>]*\b(?:id|name)=[\"']([^\"']+)[\"']", html))
    lines = rendered.splitlines()
    for index, line in enumerate(lines):
        heading = re.match(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+\s*)?$", line)
        value = heading[1] if heading else None
        if value is None and index + 1 < len(lines) and re.fullmatch(r" {0,3}(?:=+|-+)\s*", lines[index + 1]):
            value = line.strip() or None
        if value is None:
            continue
        value = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", value)
        value = re.sub(r"<[^>]*>", "", value).replace("`", "").lower()
        value = "".join(c for c in value if c in " _-" or unicodedata.category(c)[0] in "LN")
        slug = value.replace(" ", "-")
        candidate, suffix = slug, 0
        while candidate in used:
            suffix += 1
            candidate = f"{slug}-{suffix}"
        used.add(candidate)
        found.add(candidate)
    return found


def destinations(text: str) -> list[tuple[str, int]]:
    cleaned = re.sub(r"(`+).*?\1", "", prose(text))
    return [(match[1].strip("<>"), cleaned.count("\n", 0, match.start()) + 1)
            for pattern in (LINK, REFERENCE) for match in pattern.finditer(cleaned)]


def local_target(root: Path, source: Path, destination: str) -> tuple[Path, str] | None:
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return None
    path = unquote(parsed.path)
    target = (root / path.lstrip("/") if path.startswith("/") else source.parent / path) if path else source
    target = target.resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("local link escapes repository")
    return target, unquote(parsed.fragment)


def check_document(root: Path, source: Path) -> list[str]:
    if not source.resolve().is_relative_to(root.resolve()):
        return [f"{source.relative_to(root)}: Markdown source escapes repository"]
    errors: list[str] = []
    for destination, line in destinations(source.read_text(encoding="utf-8")):
        try:
            target = local_target(root, source, destination)
        except ValueError as error:
            errors.append(f"{source.relative_to(root)}:{line}: {error}: {destination}")
            continue
        if target is None:
            continue
        path, fragment = target
        if not path.exists():
            errors.append(f"{source.relative_to(root)}:{line}: missing local target: {destination}")
        elif fragment and path.is_file() and path.suffix.lower() == ".md":
            if fragment not in anchors(path.read_text(encoding="utf-8")):
                errors.append(f"{source.relative_to(root)}:{line}: missing heading fragment: {destination}")
    return errors


def check_translations(root: Path, manifest: Path) -> list[str]:
    if not manifest.resolve().is_relative_to(root.resolve()):
        raise ValueError("translation manifest must stay within repository")
    pairs = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(pairs, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in pairs.items()):
        raise ValueError("translation manifest must map canonical paths to translated paths")
    if len(set(pairs.values())) != len(pairs):
        raise ValueError("translation targets must be unique")
    errors: list[str] = []
    for canonical, translated in sorted(pairs.items()):
        for name, counterpart in ((canonical, translated), (translated, canonical)):
            source = (root / name).resolve()
            expected = (root / counterpart).resolve()
            if not source.is_relative_to(root.resolve()) or not expected.is_relative_to(root.resolve()):
                raise ValueError("translation manifest paths must stay within repository")
            if not source.is_file():
                errors.append(f"translation pair missing: {name}")
                continue
            targets = [local_target(root, source, destination) for destination, _ in destinations(source.read_text(encoding="utf-8"))]
            if not any(target is not None and target[0] == expected for target in targets):
                errors.append(f"{name}: missing reciprocal language link to {counterpart}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    output = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=root, capture_output=True, check=True).stdout
    files = sorted({root / name for name in output.decode().split("\0") if name.lower().endswith(".md")})
    errors = [error for source in files if source.is_file() for error in check_document(root, source)]
    manifest = root / "docs/translations.json"
    try:
        errors.extend(check_translations(root, manifest))
    except (OSError, ValueError) as error:
        errors.append(f"translation manifest: {error}")
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"Documentation check failed: {len(errors)} error(s).", file=sys.stderr)
        return 1
    print(f"Documentation check passed: {len(files)} Markdown files; local links/fragments and translation pairs checked.")
    print("No network requests; semantic translation equivalence and external links require human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

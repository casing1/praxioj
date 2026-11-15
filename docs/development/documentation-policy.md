# Documentation and translation policy

[한국어](../i18n/ko/development/documentation-policy.md) · [Documentation index](../README.md)

## Purpose and status

This is the reusable documentation standard for PraxiOJ development from the governance change preceding M6-A onward. It governs documentation, not runtime acceptance. M5 is the completed product baseline; creating M6-A/M6-B tracking objects does not implement either milestone.

## Source and languages

English is the canonical source. Korean is the maintained translation language. New major technical documents and substantially changed core documents should include a Korean counterpart in the same PR. Both documents link to one another; register the pair in [translations.json](../translations.json). Paths below `docs/i18n/ko/` normally mirror the canonical document's category. The project README uses `docs/i18n/ko/README.md`; the documentation index uses `docs/i18n/ko/index.md`.

Keep code identifiers, environment variables, commands, API paths, protocol values and actual technology names unchanged. Translate explanations and preserve the strength of security claims and warnings. A translation must distinguish implemented behavior, a proposed design and a test that actually ran in the same way as its source.

There is no requirement to translate all M1–M5 documentation at once. Link untranslated historical references explicitly and use a separately scoped Issue when broader translation work is needed. Do not silently replace an English source with a divergent Korean design. A known temporary lag must name the affected pair, the reason and its tracking Issue in the PR; resolve it before claiming that pair synchronized.

## Required content

A new technical document states its purpose, current status, requirements and non-goals, responsible components, trust boundaries, compatibility impact, acceptance criteria, evidence, limitations and related Issue/PR/document links. Use the relevant [template](../README.md#document-templates), adapting sections to the actual change. A design proposal is not implementation evidence. An empty template is not a validation report.

Validation records identify the tested revision and environment, commands and actual pass/fail/skip counts, unavailable paths, security tests, optimization findings and GitHub delivery. Record a measured performance improvement only with comparable before/after workloads and units. Otherwise use **"reviewed; no justified optimization"** and explain the reason.

Use relative repository links where practical. Keep existing document paths stable; if a move is necessary, update every reference in the same change. Add new documents to [docs/README.md](../README.md), and add the translated entry to the Korean index. Avoid including credentials, private participant content, local database files or sensitive log output in examples.

## README and changelog gates

Review the root README and CHANGELOG on every PR. Update README when capabilities, quickstart commands, configuration, supported environments, architecture summary, limitations or milestone status change. If unchanged, give a concrete reason in the PR. Apply the same review to its Korean counterpart.

Use [CHANGELOG.md](../../CHANGELOG.md) for user-relevant additions, changes, fixes, security controls, measured performance changes and documentation changes. New unpublished work belongs under `Unreleased`. Empty categories can be omitted. Follow Keep a Changelog style and Semantic Versioning when a release is actually made; do not invent a release, tag, date or version for historical milestones. Detailed internal refactors belong in PRs rather than duplicating every commit in the changelog.

## Checks and review

Run the repository's deterministic documentation check and inspect its actual output. It checks local Markdown destinations/headings and registered translation pairs, with no external requests. It cannot prove translation quality, technical truth, external URL availability or a security claim; reviewers must compare substance and verify commands against the changed implementation.

```sh
python3 scripts/check-docs.py
python3 -m pytest -q tests/governance
```

Before merge, confirm reciprocal links, index entries, README/CHANGELOG decisions and English/Korean consistency. The PR must retain exact test and CI evidence. Preserve Apache-2.0 licensing, contributor copyright and required third-party attribution. The project remains independent and must not imply university, laboratory or company ownership.

## References

- [Contribution process](../../CONTRIBUTING.md)
- [Engineering workflow](engineering-workflow.md)
- [PR template](../../.github/PULL_REQUEST_TEMPLATE.md)
- [AuthZest reference decisions](governance-reference.md)

# Security review template

[한국어](../i18n/ko/templates/security-review.md) · [Documentation policy](../development/documentation-policy.md)

Template only. A filled review needs evidence and a defined revision; a checklist alone is not a security certification.

## Scope

Identify the revision, changed paths, related Issue/PR, coverage and exclusions.

## Threat Model

Link the applicable model and explain changes to attackers, goals and enforcement boundaries.

## Assets & Trust Boundaries

Name protected data, identities, capabilities, systems and authority transitions.

## Assumptions

Distinguish verified prerequisites from trusted operator assumptions and unavailable environments.

## Attack Surfaces

Identify reachable inputs, identity/authorization paths, parsers, state races, resource and recovery paths.

## Security Controls

Describe actual enforcement owners and fail-closed behavior; separate planned controls from implemented ones.

## Tests & Evidence

Record executed tests, actual commands/results, manual checks and independent review artifacts.

## Findings

Describe validated findings and remediation, or state that no findings were identified within the reviewed scope. Do not infer universal safety.

## Residual Risks

Describe remaining limitations, operational dependencies and accepted trade-offs.

## Unverified Claims

Name claims that require additional hosts, credentials, deployment or OS isolation tests.

## Next Actions

Link concrete follow-up Issues, owners and acceptance criteria. Add the reciprocal translation link to the completed review.

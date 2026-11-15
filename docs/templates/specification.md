# Technical specification template

[한국어](../i18n/ko/templates/specification.md) · [Documentation policy](../development/documentation-policy.md)

Template only. Define the actual contract and implementation status; unfilled prompts are not a specification.

## Overview

State the purpose, current implementation status, Issue, Milestone and related design.

## Scope

Define covered behavior and explicit non-goals.

## Terminology

Define terms, principals and authority without renaming code identifiers.

## Data Model

Specify fields, types, required values, size limits, identity and persistence ownership.

## Interface / Protocol

Describe operations, request/result envelopes and relevant examples.

## Preconditions

State authentication, authorization, source/version, resource and runtime requirements.

## State Transitions

Define allowed transitions, terminal states, concurrency and idempotency behavior.

## Validation Rules

Specify parser, digest, resource, path and cross-resource binding checks as applicable.

## Security Invariants

Identify trust boundaries, narrow permissions, revocation and secret exclusions.

## Error Handling

Define controlled errors, timeouts, cancellation, recovery and observable outcomes.

## Versioning

State protocol/schema versions and unknown-version behavior.

## Compatibility

Describe existing callers, migration, rollback and deprecation implications.

## Test Requirements

Link positive, negative, boundary, regression and concurrency tests, actual evidence, related PR and the finished document's translation.

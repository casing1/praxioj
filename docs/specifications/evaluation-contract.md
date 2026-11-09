# Evaluation contract

`EvaluationInput` contains a validated `ProblemManifest`, an immutable `SubmissionData`, optional artifacts, authorized `TraceEnvelope` values, and evaluation configuration. The platform constructs this input after checking session ownership. Independent Python callers can construct the same input without HTTP or a database.

`SubmissionData` includes its identifier, content, and SHA-256 digest. Artifact and trace evidence use identifiers, not arbitrary filesystem access. The evaluator receives only data passed to it; it does not own database authorization or query another participant's history.

`EvaluationResult` contains:

- Evaluation identifier and status (`completed`, `failed`, or `unsupported`).
- Optional aggregate score and maximum score.
- Criterion results with scores, maximum scores, pass status, feedback, and evidence.
- Overall feedback, evidence references, evaluator identity, and evaluator version.

The API adds session, submission and problem-version context to the framework result. Aggregate scores are nullable so future evaluations can report categorical or multi-dimensional outcomes without forcing every result into one number.

## Trusted initial evaluator

The built-in evaluator in M1 and M2 is `builtin.text-rubric` version `1.0.0`. Each criterion has private `config.required_terms`. It matches all of those terms case-insensitively as substrings in the final submitted text; all present earns the criterion's maximum points, otherwise zero. Aggregate score is the sum of criterion points.

This small deterministic evaluator proves the framework flow. It is not semantic assessment, a secure plagiarism detector, or a comprehensive measure of collaboration. It currently does not grade the trace. Authors can change the declarative rubric for new problems without changing platform source.

Criterion feedback identifies the criterion outcome, while hidden required terms remain private. Evidence references identify the submission being evaluated; the engine does not fabricate explanations about unobserved behavior. Empty/invalid inputs and unsupported evaluator identities are handled explicitly.

## Execution responsibility

The evaluation contract is separate from the execution backend. The API executes this trusted built-in function synchronously, inside the submission transaction. The engine never imports a module named by a manifest, runs user-provided Python, launches a shell, or reads unrequested host files.

A future Judge Worker will accept immutable evaluation inputs, verify package/evaluator identity, start an isolated environment, enforce resource and network policy, collect artifacts, return a result, and clean up. That worker and sandbox do not exist yet. Execution interfaces intentionally fail as unavailable rather than falling back to unsafe host execution.

Regrading, multiple attempts, asynchronous retries, richer nonnumeric rubrics, and reproducible environment images are deferred. Any future retry design must preserve the original submission/version association and distinguish a new evaluation attempt from an overwritten result.

## M2 artifact and trace evidence

At final submission, the Platform stores immutable snapshots of the session's logical workspace files and passes them, together with the owner-authorized ordered trace, into `EvaluationInput`. File modifications include hashes/revisions in the trace. Subsequent writes are blocked because submission closes the session. Provider attempts, tool authorization/results, errors, and state changes can support future process rubrics. The current text rubric does not score these observations; its scoring behavior remains unchanged.

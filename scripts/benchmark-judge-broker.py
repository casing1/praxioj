#!/usr/bin/env python3
"""Compare full synthetic result validation pipelines; no database, I/O or execution.

The old two-call pipeline and combined helper run against identical fixed bytes
in the same process. This microbenchmark does not measure PostgreSQL or a sandbox.
"""
import asyncio
from datetime import UTC, datetime, timedelta
import json
import platform
import statistics
import time
import tracemalloc
from uuid import UUID

from praxioj.execution import build_mock_request, MockJudgeBackend, validate_execution_result
from praxioj.evaluation.execution import assess_synthetic_execution, validate_and_assess_synthetic_execution


def measure(function):
    for _ in range(20):
        function()
    batches = []
    for _ in range(7):
        start = time.perf_counter()
        for _ in range(100):
            function()
        batches.append((time.perf_counter() - start) * 10)
    tracemalloc.start()
    for _ in range(100):
        function()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"median_ms": statistics.median(batches), "range_ms": [min(batches), max(batches)],
        "peak_bytes_100_calls": peak}


def main():
    request = build_mock_request(request_id=UUID(int=1), job_id=UUID(int=2), attempt_id=UUID(int=3),
        session_id=UUID(int=4), fence=1, submission_id=UUID(int=5), trace_head_sha256="0" * 64,
        trace_next_sequence_number=1, deadline=datetime.now(UTC) + timedelta(seconds=60),
        criteria=[{"id": "synthetic-criterion", "title": "Synthetic criterion", "max_score": 100.0}])
    raw = asyncio.run(MockJudgeBackend().execute(request))
    def before():
        return validate_execution_result(request, raw), assess_synthetic_execution(request, raw)
    def after():
        return validate_and_assess_synthetic_execution(request, raw)
    assert before() == after(), "The combined path changed validation or assessment"
    print(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
        "samples_per_pipeline": 700, "batches": 7, "batch_size": 100,
        "raw_result_bytes": len(json.dumps(raw, separators=(",", ":")).encode()),
        "two_full_validations": measure(before), "one_full_validation": measure(after)}, indent=2))


if __name__ == "__main__":
    main()

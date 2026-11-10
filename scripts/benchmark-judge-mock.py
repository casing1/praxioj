#!/usr/bin/env python3
"""Compare equivalent duplicate/current Mock parsing on the same current binary.

Synthetic in-memory fixture only: no database, subprocess, files, network or code
execution. The duplicate path simulates the earlier redundant request parse; it
is not an old-version benchmark or a measurement of actual Judge execution.
"""
import asyncio
from datetime import UTC, datetime
import json
import os
import statistics
import sys
from time import perf_counter
import tracemalloc
from uuid import UUID

from praxioj.execution import MockJudgeBackend, build_mock_request, canonical_json, parse_execution_request


async def main():
    request = build_mock_request(request_id=UUID(int=1), job_id=UUID(int=2), attempt_id=UUID(int=3),
        session_id=UUID(int=4), submission_id=UUID(int=5), fence=1, trace_head_sha256=None,
        trace_next_sequence_number=1, deadline=datetime(2099, 1, 1, tzinfo=UTC),
        criteria=[{"id": "synthetic", "title": "Synthetic criterion", "max_score": 100.0}])
    backend = MockJudgeBackend()

    async def duplicate_parse():
        return await backend.execute(parse_execution_request(request))

    async def current_parse():
        return await backend.execute(request)

    assert await duplicate_parse() == await current_parse(), "Comparison paths changed fixture behavior"
    results = {}
    for label, invoke in (("equivalent_duplicate_parse", duplicate_parse), ("current_single_parse", current_parse)):
        for _ in range(20):
            await invoke()
        batches = []
        for _ in range(7):
            started = perf_counter()
            for _ in range(500):
                await invoke()
            batches.append((perf_counter() - started) * 1000 / 500)
        tracemalloc.start()
        for _ in range(100):
            await invoke()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        results[label] = {"median_ms": statistics.median(batches),
            "range_ms": [min(batches), max(batches)], "peak_bytes_100_calls": peak}
    print(json.dumps({"python": sys.version.split()[0], "platform": sys.platform,
        "machine": os.uname().machine if hasattr(os, "uname") else "unverified",
        "request_bytes": len(canonical_json(request)), "warmups": 20, "batches": 7,
        "calls_per_batch": 500, "calls_per_path": 3500,
        "comparison": "Same-version equivalent redundant parse versus current single parse; no actual runner",
        "results": results}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

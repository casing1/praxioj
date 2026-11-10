#!/usr/bin/env python3
"""Real HTTP account → durable worker → tool → evidence rubric smoke (Mock default)."""
from pathlib import Path
import runpy
import sys

if __name__ == "__main__":
    sys.argv.extend(["--problem", "evidence-plan"])
    runpy.run_path(str(Path(__file__).with_name("smoke-m2.py")), run_name="__main__")

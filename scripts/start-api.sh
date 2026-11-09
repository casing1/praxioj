#!/bin/sh
set -eu
alembic -c apps/api/alembic.ini upgrade head
python -m praxioj_api.cli register examples/problems/release-plan
python -m praxioj_api.cli register examples/problems/workspace-plan
exec uvicorn praxioj_api.main:app --host 0.0.0.0 --port 8000

.PHONY: install test test-python test-web build-web migrate register api worker web up down

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install -c requirements.lock -e packages/framework -e 'apps/api[test]'
	npm --prefix apps/web ci

test: test-python test-web build-web

test-python:
	.venv/bin/python -m pytest

test-web:
	npm --prefix apps/web test -- --run

build-web:
	npm --prefix apps/web run build

migrate:
	.venv/bin/alembic -c apps/api/alembic.ini upgrade head

register:
	.venv/bin/python -m praxioj_api.cli register examples/problems/release-plan
	.venv/bin/python -m praxioj_api.cli register examples/problems/workspace-plan
	.venv/bin/python -m praxioj_api.cli register examples/problems/evidence-plan

api:
	.venv/bin/uvicorn praxioj_api.main:app --host 127.0.0.1 --port 8000 --reload

worker:
	.venv/bin/python -m praxioj_api.worker

web:
	npm --prefix apps/web run dev -- --host 127.0.0.1

up:
	docker compose up --build -d --wait

down:
	docker compose down

.PHONY: lint lint-fix lint-typecheck test db-up db-down db-init db-smoke run-ingest run-extract run-bench run-web

db-up:
	docker compose up -d db

db-down:
	docker compose down

lint:
	uv run ruff check sumnews tests

lint-fix:
	uv run ruff check --fix sumnews tests

lint-typecheck:
	uv run mypy sumnews

test:
	uv run pytest $(ARGS)

db-init:
	uv run python scripts/db_init.py

db-smoke:
	uv run python scripts/db_smoke.py

run-ingest:
	uv run python scripts/run_ingest.py $(ARGS)

run-extract:
	uv run python scripts/run_extract.py $(ARGS)

run-bench:
	uv run python scripts/run_bench.py $(ARGS)

run-web:
	uv run uvicorn sumnews.app:create_app --factory --reload

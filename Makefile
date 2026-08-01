.PHONY: sync install lint format type test test-cov test-parallel clean

## Install/sync dependencies (creates .venv and uv.lock)
sync:
	uv sync

install: sync

## Lint (ruff check + format check)
lint:
	uv run ruff check .
	uv run ruff format --check .

## Auto-fix and format
format:
	uv run ruff check --fix .
	uv run ruff format .

## Type check the framework
type:
	uv run mypy

## Run tests
test:
	uv run pytest

## Run tests with parallel execution (pytest-xdist)
test-parallel:
	uv run pytest -n auto

## Run tests with coverage
test-cov:
	uv run pytest --cov=framework --cov-report=term-missing

## Remove caches and coverage artifacts
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov

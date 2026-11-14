.PHONY: ci-install ci-quality ci-generated ci-package ci-promptfoo ci-docs benchmark

ci-install:
	uv sync --frozen --all-groups

ci-quality:
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .
	uv run --frozen mypy src tests examples scripts benchmarks
	uv run --frozen python scripts/check_import_boundaries.py --src src
	uv run --frozen pytest -m "not live and not promptfoo" --cov=prompt_contracts --cov-branch --cov-report=xml --cov-report=term-missing --cov-fail-under=90

ci-generated:
	uv run --frozen pytest tests/integration/test_reference_schemas.py
	uv run --frozen prompt-contracts lint examples/contracts
	uv run --frozen prompt-contracts verify examples/contracts --lock examples/contracts.lock.json
	uv run --frozen prompt-contracts verify tests/fixtures/consumers/ace_your_interview/contracts --lock tests/fixtures/consumers/ace_your_interview/contracts.lock.json
	uv run --frozen prompt-contracts verify tests/fixtures/consumers/job_hunting_assistant/contracts --lock tests/fixtures/consumers/job_hunting_assistant/contracts.lock.json

ci-package:
	rm -rf dist
	uv build
	uv run --frozen twine check --strict dist/*
	uv run --frozen python scripts/verify_distribution.py --dist-dir dist

ci-promptfoo:
	npm --prefix tools/promptfoo ci --no-audit --no-fund
	uv run --frozen pytest -m promptfoo tests/adapters/test_promptfoo_cli.py

ci-docs:
	uv run --frozen mkdocs build --strict

benchmark:
	uv run --frozen python benchmarks/runtime.py --iterations 1000

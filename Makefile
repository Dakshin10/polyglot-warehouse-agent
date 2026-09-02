.PHONY: install lint typecheck test test-all audit config verify clean

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/

test:
	pytest

test-all:
	pytest -m ""

config:
	pwa config

audit:
	pwa audit

verify:
	pwa source verify && pwa warehouse verify

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -not -path "./venv/*" -exec rm -rf {} +

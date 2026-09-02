.PHONY: install lint typecheck test test-all verify clean

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

verify:
	pwa source verify && pwa warehouse verify

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

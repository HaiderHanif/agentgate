.PHONY: install lint type test cov check clean

install:
	python -m pip install -e ".[dev,mcp]"

lint:
	ruff check src tests
	ruff format --check src tests

type:
	mypy

test:
	pytest

cov:
	pytest --cov=agentgate --cov-report=term-missing --cov-report=xml

check: lint type test

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -name "__pycache__" -type d -exec rm -rf {} +

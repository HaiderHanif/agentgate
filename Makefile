.DEFAULT_GOAL := help
.PHONY: help install hooks lint format type test cov gate example build clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with development dependencies
	pip install -e ".[dev,mcp]"

hooks: ## Install pre-commit hooks
	pre-commit install

lint: ## Run the linter
	ruff check .

format: ## Format the codebase
	ruff format .
	ruff check --fix .

type: ## Run static type checking
	mypy

test: ## Run the test suite
	pytest

cov: ## Run tests with a coverage report
	pytest --cov=agentgate --cov-report=term-missing

gate: ## Replay the example agent through the CLI
	agentgate verify \
		examples.refund_agent.agent:handle_refund \
		examples/refund_agent/traces/refund_flow.json

example: ## Run the worked example
	pytest examples/refund_agent -v

check: lint type test ## Run every check CI runs

build: ## Build the distribution
	python -m build

clean: ## Remove build and cache artifacts
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +

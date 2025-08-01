.PHONY: help install dev-install format lint typecheck test test-cov run clean

# Default target
help:
	@echo "Available commands:"
	@echo "  install     - Install project dependencies"
	@echo "  dev-install - Install project with dev dependencies"
	@echo "  format      - Format code with ruff"
	@echo "  lint        - Lint code with ruff"
	@echo "  lint-fix    - Lint and auto-fix code with ruff"
	@echo "  typecheck   - Run type checking with mypy"
	@echo "  test        - Run tests with pytest"
	@echo "  test-cov    - Run tests with coverage report"
	@echo "  run         - Run the application"
	@echo "  clean       - Clean build artifacts and cache"

# Installation
install:
	uv sync --no-dev

dev-install:
	uv sync --extra dev

# Code quality
format:
	uv run ruff format .

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

typecheck:
	uv run mypy .

# Testing
test:
	uv run pytest

test-cov:
	uv run pytest --cov=. --cov-report=html --cov-report=term

# Running
run:
	uv run python app.py

# Maintenance
clean:
	rm -rf .ruff_cache/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
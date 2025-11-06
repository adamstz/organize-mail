.PHONY: help test test-all test-unit test-smoke test-llm test-storage test-jobs test-api test-cov lint format clean

# Python virtual environment
VENV_PATH = ../.venv
PYTHON = $(VENV_PATH)/bin/python
PYTEST = $(PYTHON) -m pytest

# Default target
help:
	@echo "Available test commands:"
	@echo "  make test           - Run all tests (default)"
	@echo "  make test-all       - Run all tests with verbose output"
	@echo "  make test-unit      - Run unit tests only"
	@echo "  make test-smoke     - Run smoke tests only"
	@echo "  make test-llm       - Run LLM processor tests only"
	@echo "  make test-storage   - Run storage tests only"
	@echo "  make test-jobs      - Run job tests only"
	@echo "  make test-api       - Run API tests only"
	@echo "  make test-cov       - Run tests with coverage report"
	@echo "  make lint           - Run flake8 linter"
	@echo "  make format         - Format code with black"
	@echo "  make clean          - Remove cache and temp files"

# Run all tests
test:
	PYTHONPATH=. $(PYTEST) tests/ -v

# Run all tests with extra verbosity
test-all:
	PYTHONPATH=. $(PYTEST) tests/ -vv --tb=short

# Run only unit tests (excludes smoke)
test-unit:
	PYTHONPATH=. $(PYTEST) tests/ -v --ignore=tests/smoke/

# Run smoke tests only
test-smoke:
	PYTHONPATH=. $(PYTEST) tests/test_smoke.py -v

# Run LLM processor tests only
test-llm:
	PYTHONPATH=. $(PYTEST) tests/test_llm_processor.py -v

# Run storage tests only
test-storage:
	PYTHONPATH=. $(PYTEST) tests/test_storage.py -v

# Run job tests only
test-jobs:
	PYTHONPATH=. $(PYTEST) tests/test_jobs.py -v

# Run API tests only
test-api:
	PYTHONPATH=. $(PYTEST) tests/test_api_messages.py -v

# Run tests with coverage report
test-cov:
	PYTHONPATH=. $(PYTEST) tests/ --cov=src/ --cov-report=term-missing --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

# Run linter
lint:
	$(PYTHON) -m flake8 src/ --count --select=E9,F63,F7,F82 --show-source --statistics
	$(PYTHON) -m flake8 src/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# Format code (requires black)
format:
	$(PYTHON) -m black src/ tests/

# Clean up cache and temp files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete
	find . -type f -name "coverage.xml" -delete
	@echo "Cleaned up cache and temporary files"

# Quick test (fast, no coverage)
test-quick:
	PYTHONPATH=. $(PYTEST) tests/ -x --tb=line

# Watch mode (requires pytest-watch)
test-watch:
	PYTHONPATH=. $(PYTHON) -m ptw tests/ -- -v

# Run specific test file
test-file:
	@test -n "$(FILE)" || (echo "Usage: make test-file FILE=tests/test_example.py" && exit 1)
	PYTHONPATH=. $(PYTEST) $(FILE) -v

# Run specific test function
test-func:
	@test -n "$(FUNC)" || (echo "Usage: make test-func FUNC=test_function_name" && exit 1)
	PYTHONPATH=. $(PYTEST) -k "$(FUNC)" -v

.PHONY: help install install-dev test lint verify format bench bench-mock bench-live report clean docker-build docker-bench

PYTHON_MIN_VERSION := 3.11
PYTHON_CANDIDATES = $(VENV)/bin/python python3.13 python3.12 python3.11 python3
BOOTSTRAP_PYTHON ?= $(shell for py in $(PYTHON_CANDIDATES); do \
	if command -v $$py >/dev/null 2>&1 && $$py -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then \
		command -v $$py; \
		break; \
	fi; \
done)
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(PY) -m pip
VENV_STAMP := $(VENV)/.installed-dev

help:
	@echo "Targets:"
	@echo "  install       Install runtime dependencies"
	@echo "  install-dev   Install runtime + dev dependencies"
	@echo "  test          Run pytest against the mock-LLM test suite"
	@echo "  lint          Run ruff against src/ and tests/"
	@echo "  format        Run black and ruff --fix"
	@echo "  bench         Run the full benchmark (uses mock LLM by default)"
	@echo "  bench-mock    Explicit alias for bench against the mock LLM"
	@echo "  bench-live    Run the benchmark against real LLM APIs"
	@echo "  report        Re-render reports from the newest results file"
	@echo "  clean         Remove build artifacts and __pycache__"
	@echo "  docker-build  Build the Docker image"
	@echo "  docker-bench  Run the benchmark inside Docker"

.PHONY: check-bootstrap-python

check-bootstrap-python:
	@if [ -z "$(BOOTSTRAP_PYTHON)" ]; then \
		echo "Python $(PYTHON_MIN_VERSION)+ is required." >&2; \
		echo "Install Python $(PYTHON_MIN_VERSION)+ or run: make BOOTSTRAP_PYTHON=/path/to/python$(PYTHON_MIN_VERSION) <target>" >&2; \
		exit 1; \
	fi
	@$(BOOTSTRAP_PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || { \
		echo "BOOTSTRAP_PYTHON=$(BOOTSTRAP_PYTHON) is not Python $(PYTHON_MIN_VERSION)+." >&2; \
		exit 1; \
	}

$(VENV_STAMP): pyproject.toml requirements.txt | check-bootstrap-python
	@if [ ! -x "$(PY)" ] || ! $(PY) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then \
		rm -rf $(VENV); \
		$(BOOTSTRAP_PYTHON) -m venv $(VENV); \
	fi
	@if ! $(PY) -m pip --version >/dev/null 2>&1; then \
		$(PY) -m ensurepip --upgrade; \
	fi
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	touch $(VENV_STAMP)

install install-dev: check-bootstrap-python $(VENV_STAMP)

test: install-dev
	$(PY) -m pytest tests/ -v

lint: install-dev
	$(PY) -m ruff check src tests

verify: lint test

format: install-dev
	$(PY) -m black src tests
	$(PY) -m ruff check --fix src tests

bench: bench-mock

bench-mock: install-dev
	$(PY) -m scripts.run_bench --frameworks all --output results/latest.json

bench-live: install-dev
	USE_MOCK_LLM=0 $(PY) -m scripts.run_bench --frameworks all --output results/latest.json

report: install-dev
	$(PY) -m scripts.run_bench --report-only --input results/latest.json

clean:
	rm -rf $(VENV) build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker compose build benchmark

docker-bench:
	docker compose run --rm benchmark

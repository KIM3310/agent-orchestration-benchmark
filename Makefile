.PHONY: help install install-dev test lint verify format bench bench-mock bench-live report clean docker-build docker-bench

BOOTSTRAP_PYTHON ?= python3
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

$(VENV_STAMP): pyproject.toml requirements.txt
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

install install-dev: $(VENV_STAMP)

test: install-dev
	$(PY) -m pytest tests/ -v

lint: install-dev
	$(PY) -m ruff check src tests

verify: lint test

format: install-dev
	$(PY) -m black src tests
	$(PY) -m ruff check --fix src tests

bench: bench-mock

bench-mock:
	$(PY) -m scripts.run_bench --frameworks all --output results/latest.json

bench-live:
	USE_MOCK_LLM=0 $(PY) -m scripts.run_bench --frameworks all --output results/latest.json

report:
	$(PY) -m scripts.run_bench --report-only --input results/latest.json

clean:
	rm -rf $(VENV) build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker compose build benchmark

docker-bench:
	docker compose run --rm benchmark

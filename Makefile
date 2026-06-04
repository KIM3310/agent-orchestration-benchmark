.PHONY: help install install-dev test lint verify format bench bench-mock bench-live report clean docker-build docker-bench

PY := python3
PIP := $(PY) -m pip

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

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -e ".[dev]"

test:
	$(PY) -m pytest tests/ -v

lint:
	$(PY) -m ruff check src tests

verify: lint test

format:
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
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker compose build benchmark

docker-bench:
	docker compose run --rm benchmark

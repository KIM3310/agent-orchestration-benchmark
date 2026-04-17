"""Benchmark configuration: model IDs, pricing tables, timeouts, retry budgets.

All framework runners read from this module so swapping the target model or
updating a pricing number only requires a single-point edit. Keep this file
free of imports from other project modules to avoid circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
RESULTS_DIR: Path = PROJECT_ROOT / "results"
FIXTURES_DIR: Path = PROJECT_ROOT / "fixtures"


# ---------------------------------------------------------------------------
# Model + pricing
# ---------------------------------------------------------------------------
# USD per 1,000,000 tokens. Update on pricing changes; keep as a single source
# of truth so cost metrics stay comparable across frameworks.
PRICING_USD_PER_MTOK: Dict[str, Dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-4o": {"input": 2.500, "output": 10.000},
    "claude-3-5-sonnet": {"input": 3.000, "output": 15.000},
    "claude-3-5-haiku": {"input": 0.800, "output": 4.000},
}

DEFAULT_MODEL: str = "gpt-4o-mini"
DEFAULT_TEMPERATURE: float = 0.0
DEFAULT_MAX_TOKENS: int = 1024


# ---------------------------------------------------------------------------
# Reliability budgets
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RetryPolicy:
    """Retry behaviour for individual tool calls and the outer agent loop."""

    max_retries: int = 3
    initial_backoff_s: float = 0.25
    backoff_multiplier: float = 2.0
    max_backoff_s: float = 8.0


DEFAULT_RETRY_POLICY: RetryPolicy = RetryPolicy()


@dataclass(frozen=True)
class TimeoutConfig:
    """Hard wall-clock timeouts for the agent loop. Seconds."""

    per_tool_call_s: float = 15.0
    per_prompt_s: float = 60.0
    whole_benchmark_s: float = 3600.0


DEFAULT_TIMEOUTS: TimeoutConfig = TimeoutConfig()


# ---------------------------------------------------------------------------
# Benchmark knobs
# ---------------------------------------------------------------------------
@dataclass
class BenchmarkConfig:
    """Top-level configuration for a benchmark run.

    Values here are the defaults picked up by ``src.runner.BenchmarkRunner``.
    CLI callers can override them via a YAML/JSON file or environment variables
    in a future revision; for now we surface them as simple dataclass fields.
    """

    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    retry: RetryPolicy = field(default_factory=lambda: DEFAULT_RETRY_POLICY)
    timeouts: TimeoutConfig = field(default_factory=lambda: DEFAULT_TIMEOUTS)
    seed: int = 2026_04_16
    # How many times to re-run each prompt to estimate deterministic-replay
    # rate. 3 is the smallest sample size that can produce a non-trivial ratio.
    replay_trials: int = 3
    # Whether to use mock LLM clients instead of real API calls. CI defaults to
    # True so tests can run without an API key; set to False for real runs.
    use_mock_llm: bool = True


def cost_for_tokens(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return the USD cost of a request given its input/output token counts.

    Falls back to the default model's pricing if ``model`` is unknown, so the
    benchmark never crashes on a typo but the report will surface the
    discrepancy via the model-name column.
    """
    table = PRICING_USD_PER_MTOK.get(model, PRICING_USD_PER_MTOK[DEFAULT_MODEL])
    return (tokens_in * table["input"] + tokens_out * table["output"]) / 1_000_000.0

"""Metric collectors and aggregators used by the benchmark runner.

All metric computation lives here so framework runners can focus on
integration and leave numerical consistency to a single module.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .config import cost_for_tokens
from .fixtures import Prompt
from .task import ToolCallRecord


# ---------------------------------------------------------------------------
# Per-prompt observation
# ---------------------------------------------------------------------------
@dataclass
class PromptObservation:
    """The raw data captured for a single prompt execution.

    Runners build one of these per prompt; the aggregator folds lists of them
    into :class:`FrameworkSummary` objects.
    """

    prompt_id: str
    framework: str
    final_answer: str
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    retry_count: int = 0
    exception: str = ""
    replay_fingerprints: List[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out


# ---------------------------------------------------------------------------
# Individual metric primitives
# ---------------------------------------------------------------------------
def tool_call_success(obs: PromptObservation, prompt: Prompt) -> bool:
    """Return True iff the observed tool sequence matches the expected one.

    The comparison is strict in ordering and tool name. Missing or extra tools
    count as a failure, which keeps the metric honest for frameworks that
    cheerfully over-call.
    """
    observed = [c.name for c in obs.tool_calls if c.ok]
    return observed == list(prompt.expected_tool_sequence)


def answer_quality(obs: PromptObservation, prompt: Prompt) -> bool:
    """Return True if the final answer satisfies the prompt's grading rules."""
    return prompt.answer_matches(obs.final_answer or "")


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile that works for small samples without numpy."""
    if not values:
        return 0.0
    xs = sorted(values)
    k = max(0, min(len(xs) - 1, int(round((pct / 100.0) * (len(xs) - 1)))))
    return float(xs[k])


# ---------------------------------------------------------------------------
# Framework-level summary
# ---------------------------------------------------------------------------
@dataclass
class FrameworkSummary:
    """Aggregated metrics for a single framework across all prompts."""

    framework: str
    n_prompts: int
    tool_call_success_rate: float
    final_answer_quality: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    tokens_in: int
    tokens_out: int
    total_cost_usd: float
    retry_count: int
    exception_rate: float
    deterministic_replay_rate: float

    def as_row(self) -> Dict[str, float | str | int]:
        return {
            "framework": self.framework,
            "n_prompts": self.n_prompts,
            "tool_call_success_rate": round(self.tool_call_success_rate, 4),
            "final_answer_quality": round(self.final_answer_quality, 4),
            "latency_p50_ms": round(self.latency_p50_ms, 2),
            "latency_p95_ms": round(self.latency_p95_ms, 2),
            "latency_p99_ms": round(self.latency_p99_ms, 2),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "retry_count": self.retry_count,
            "exception_rate": round(self.exception_rate, 4),
            "deterministic_replay_rate": round(self.deterministic_replay_rate, 4),
        }


def aggregate(
    observations: List[PromptObservation],
    prompts: Dict[str, Prompt],
    model: str,
) -> FrameworkSummary:
    """Fold a list of per-prompt observations into a framework summary."""
    if not observations:
        raise ValueError("aggregate() requires at least one observation")

    framework = observations[0].framework
    n = len(observations)

    successes = [tool_call_success(o, prompts[o.prompt_id]) for o in observations]
    qualities = [answer_quality(o, prompts[o.prompt_id]) for o in observations]
    latencies = [o.latency_ms for o in observations]

    tokens_in = sum(o.tokens_in for o in observations)
    tokens_out = sum(o.tokens_out for o in observations)
    total_cost = cost_for_tokens(model, tokens_in, tokens_out)

    retry_count = sum(o.retry_count for o in observations)
    exceptions = sum(1 for o in observations if o.exception)

    replay_rate = _deterministic_replay_rate(observations)

    return FrameworkSummary(
        framework=framework,
        n_prompts=n,
        tool_call_success_rate=sum(successes) / n,
        final_answer_quality=sum(qualities) / n,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        latency_p99_ms=percentile(latencies, 99),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_cost_usd=total_cost,
        retry_count=retry_count,
        exception_rate=exceptions / n,
        deterministic_replay_rate=replay_rate,
    )


def _deterministic_replay_rate(observations: List[PromptObservation]) -> float:
    """Fraction of prompts whose replay-fingerprint list contains only one
    unique value (i.e. every replay produced the same tool-call sequence)."""
    if not observations:
        return 0.0
    stable = 0
    for o in observations:
        if o.replay_fingerprints and len(set(o.replay_fingerprints)) == 1:
            stable += 1
    return stable / len(observations)


def mean(values: Sequence[float]) -> float:
    """Safe mean; zero on empty input."""
    return statistics.fmean(values) if values else 0.0

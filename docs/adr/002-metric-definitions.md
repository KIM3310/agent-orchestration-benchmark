# ADR 002: Metric Definitions

* **Status:** Accepted
* **Date:** 2026-04-16
* **Author:** Doeon Kim

## Context

Operators running agents in production consistently ask four questions:

1. Does the agent call the right tool? (correctness)
2. Does the agent produce an answer a user will accept? (quality)
3. How much did it cost? (unit economics)
4. Will the same input produce the same calls? (reproducibility)

Published agent benchmarks often optimise for (2) while ignoring (1), (3),
and (4). That mismatch is why benchmark "winners" under-perform when
shipped.

## Decision

Every run emits a single summary row per framework with the following
metrics:

| Metric | Category | Notes |
|---|---|---|
| `tool_call_success_rate` | correctness | Exact match of observed tool sequence against expected. Extra calls count as failures. |
| `final_answer_quality` | quality | Keyword + regex grade. Conservative by design. |
| `latency_p50_ms / p95_ms / p99_ms` | cost | Wall-clock per-prompt percentiles. |
| `tokens_in / tokens_out` | cost | Summed across tool-calling rounds. |
| `total_cost_usd` | cost | Derived from the scope table in `src/config.py`. |
| `retry_count` | correctness | Counts adapter-initiated retries only. |
| `exception_rate` | correctness | Fraction of prompts that threw at any depth. |
| `deterministic_replay_rate` | reproducibility | Fraction of prompts whose fingerprints agree across replays. |

## Why these and not others

* **Why not F1 on extracted data?** The mock LLM keeps the benchmark
  reproducible, but a numeric correctness metric would depend on the exact
  numbers the mock happens to emit. Keyword matching accepts a broader
  range of surface forms.
* **Why percentiles, not means?** Agent latency distributions are heavy-
  tailed. Means hide the worst cases; operators care about the worst cases.
* **Why nearest-rank percentile?** Explicit, dependency-free, and stable for
  small samples. The alternative (linear interpolation) adds numerical
  subtlety without helping the reader.

## Consequences

* The grading rubric is deliberately tight. Prompts must be updated in
  lockstep with tool implementations.
* Adding a new metric means extending `FrameworkSummary.as_row` and the
  report templates. Both live in one file each (`metrics.py`, `report.py`)
  to keep the change radius small.

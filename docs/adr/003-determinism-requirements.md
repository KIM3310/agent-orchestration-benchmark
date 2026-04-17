# ADR 003: Determinism Requirements

* **Status:** Accepted
* **Date:** 2026-04-16
* **Author:** Doeon Kim

## Context

Agent frameworks introduce non-determinism at many layers: LLM sampling,
asynchronous tool dispatch, internal random IDs, concurrent node execution.
Operators need to know which of those layers their chosen framework leaks
to the caller.

A comparison that does not measure determinism flatters non-deterministic
orchestrators by hiding their biggest production failure mode.

## Decision

Determinism is a first-class metric (`deterministic_replay_rate`) with a
deliberately strict definition:

* For each prompt, the runner executes the framework
  `config.replay_trials` times (default 3).
* Each execution produces a fingerprint string built from the per-call
  hashes in `src/task.py::ToolCallRecord.fingerprint`.
* A prompt is "stable" iff all fingerprints collapse to a single unique
  value.
* `deterministic_replay_rate = stable_prompts / n_prompts`.

The `MockLLM` in `src/runners/base.py` is fully deterministic. Any
non-determinism observed in mock mode is therefore attributable to the
framework, not the LLM. That is the whole point.

## Why strict matching

A softer rule (e.g. "match on tool names only, allow argument drift") would
hide legitimate bugs. Tool arguments are what distinguish a correct call
from an incorrect one in production; a framework that routes the same
prompt to `summarize_trend(data_a=X, data_b=Y)` one day and to
`summarize_trend(data_a=Y, data_b=X)` the next day is not deterministic.

## Consequences

* Framework adapters must not inject random IDs into tool arguments.
  Stable IDs are provided via the `id` field on the raw tool-call dict.
* The fingerprint hash truncates to 16 hex chars. Accidental collisions are
  possible but negligible at 20-prompt scale.
* If a future adapter wraps a multithreaded executor, it must serialise
  tool calls before recording fingerprints. The `BenchmarkRunner` assumes
  single-threaded ordering.

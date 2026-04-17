# Methodology

This document describes how the benchmark is constructed, what invariants it
guarantees, and how each metric is computed. Read it in full before citing
numbers from a run.

## Design principles

1. **Apples-to-apples**: every framework solves the same task with the same
   tools and the same LLM back-end. Divergent metrics must be attributable to
   orchestrator behaviour, not model or data noise.
2. **Deterministic by default**: tool implementations and the mock LLM are
   seeded. Any framework that fails the `deterministic_replay_rate` metric is
   exposing non-determinism in its own control flow.
3. **Auditable**: every tool call is recorded with arguments, success flag,
   and a fingerprint hash. Result files are plain JSON so downstream
   analysis requires no SDK.
4. **Runnable offline**: CI runs the benchmark in `use_mock_llm=True` mode so
   no API key is ever required to reproduce numbers for the orchestrator
   shape itself.

## Task

Each framework must:

1. Accept a natural-language analytics request.
2. Call `query_sales_data(sql)` to retrieve rows from an in-memory SQLite
   populated with a deterministic sales dataset.
3. Call `summarize_trend(data_a, data_b)` to produce a comparative paragraph.
4. Return the paragraph as its final answer.

Both tools are deterministic: `query_sales_data` executes SQL against a
fixed table, `summarize_trend` is a closed-form function of its inputs.
Neither calls a nested LLM.

## Prompts

Twenty prompts live in `fixtures/benchmark_prompts.jsonl`. Each record
carries:

* `prompt_id` — stable identifier
* `user_message` — the request shown to the agent
* `expected_tool_sequence` — ordered list of tool names the agent must call
* `answer_keywords` — tokens that must appear (case-insensitively) in the
  final answer
* `answer_regex` — an additional pattern that must match
* `difficulty` — `easy | medium | hard`, used for slicing reports

Prompts are phrased differently but share a structural shape: compare one
quarter's sales data to another's, and summarize. This lets the benchmark
isolate orchestration behaviour from task comprehension.

## Metrics

All metrics are computed in `src/metrics.py`. Definitions are intentionally
conservative: the benchmark is meant to reward frameworks that do the right
thing, not frameworks that happen to pass through a generous grader.

| Metric | Formula | Why it matters |
|---|---|---|
| `tool_call_success_rate` | `correct_sequence_count / n_prompts` | Did the agent call the expected tools in the right order? |
| `final_answer_quality` | `answer_match_count / n_prompts` | Does the textual answer pass keyword + regex grading? |
| `latency_p50_ms / p95_ms / p99_ms` | nearest-rank percentile over per-prompt wall time | Operators care about tail latency, not just average. |
| `tokens_in / tokens_out` | sum of per-call token counts | Cost and throughput upstream of pricing. |
| `total_cost_usd` | `tokens_in * price_in + tokens_out * price_out` | Concrete dollar number for budget estimation. |
| `retry_count` | sum of explicit retry increments | Indicates fragility of tool-call parsing. |
| `exception_rate` | `observations_with_exception / n_prompts` | How often the orchestrator crashes. |
| `deterministic_replay_rate` | fraction of prompts whose replay fingerprints collapse to a single value | Whether the same input yields the same tool calls. |

## Replay and determinism

For each prompt we run the framework `config.replay_trials` times
(default 3) and collect a fingerprint of each run's tool-call sequence. The
`deterministic_replay_rate` metric is the fraction of prompts whose
fingerprints are all identical. A value below 1.0 indicates the framework
introduced non-determinism even though the LLM, tools, and prompts were all
seeded.

## Pricing

Costs come from `PRICING_USD_PER_MTOK` in `src/config.py`. Update that table
when a model's pricing changes. The benchmark never silently assumes a
price; unknown models fall back to the default (`gpt-4o-mini`) and the
report surfaces the model name so you can spot inconsistencies.

## Live vs mock mode

`use_mock_llm=True` (CI default) uses a built-in deterministic mock. Its
purpose is to exercise orchestration shape; it is not a replacement for a
real LLM. When you need to compare frameworks on real model behaviour, run
`make bench-live` with `OPENAI_API_KEY` in the environment.

## Reproducing a run

```bash
make install-dev
make test           # all unit tests pass
make bench          # mock-LLM benchmark, writes results/latest.json
python -m scripts.run_bench --report-only --input results/latest.json
```

To bind a run to a specific release tag, commit the JSON and reference it
in the accompanying report file.

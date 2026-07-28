# Interpreting Results

This guide walks through the output of `make bench` and explains how to
reason about the numbers.

## Output files

After a run you will find the following under `results/`:

| File | Format | Purpose |
|---|---|---|
| `<stem>.json` | JSON | Machine-readable results including per-prompt observations. |
| `<stem>.md`   | Markdown | Human-readable tables, safe to paste into a PR. |
| `<stem>.html` | HTML | Standalone report with prompt contracts and expandable tool-call evidence. |

Every report derives from the same result artifact. A stable `prompt_id`
plus the embedded prompt contract lets you audit or diff a run even if the
fixture later changes.

## Framework summary table

The summary table has one row per framework with every metric from
`methodology.md`. A few rules of thumb:

* `tool_call_success_rate < 1.0` means the framework did not reliably emit
  the expected tool sequence. Inspect the observations table for the
  offending prompts.
* `deterministic_replay_rate < 1.0` is a *correctness* signal. It means the
  framework reached different tool calls on different replays of the same
  prompt against the same LLM.
* `retry_count > 0` with mock LLM indicates the parser choked on a
  well-formed payload. That is usually a tool-schema bug in the adapter.
* `latency_p99 / latency_p50 > 5` suggests an orchestrator stalls on some
  prompts — often due to retry back-off or framework-internal rate limits.

## Per-prompt observations

The per-prompt section lists, for each prompt, the tool calls observed,
latency, and token usage. Use this when a summary number looks suspicious:

1. Filter by `framework` to compare two orchestrators on the same prompt.
2. Check `retry_count` on rows that failed `tool_call_success` to tell
   malformed-argument failures from wrong-tool-choice failures.
3. Verify `replay_fingerprints` is a length-3 list of identical strings for
   determinism-critical deployments.

## Common pitfalls

* **Mock mode misread.** Numbers labeled `MOCK / SYNTHETIC` measure the
  orchestrator shape, not the upstream model.
* **Configured live mode overclaim.** `LIVE / CONFIGURED` means the live path
  was requested. It is provider-verified only after adapter exceptions, token
  counters, and provider-side logs confirm actual traffic.
* **Ignoring replay rate.** A framework can post a high tool-call success
  rate while being non-deterministic. Both matter; neither substitutes for
  the other.
* **Cost as the only axis.** The cheapest framework is often the one that
  gives up earliest. Cross-reference `total_cost_usd` with
  `tool_call_success_rate` to avoid that trap.

## Recommended workflow

1. Run `make bench` on every PR that touches a runner.
2. Commit the resulting `results/` artefacts to a `results-history/`
   directory (outside version control if they are large) and link them from
   the PR description.
3. Use `scripts/run_bench.py --report-only --input <path>` to regenerate
   reports without re-running the benchmark.

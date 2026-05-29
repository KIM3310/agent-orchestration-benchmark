# agent-orchestration-benchmark

> Standardized benchmark suite comparing LLM agent orchestration frameworks on a shared task. Measures reliability, latency, cost, and deterministic replay — the metrics that matter for production operators.

[![CI](https://github.com/KIM3310/agent-orchestration-benchmark/actions/workflows/ci.yml/badge.svg)](https://github.com/KIM3310/agent-orchestration-benchmark/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

---

## Product and Review Surface

A benchmark suite that lets teams compare orchestration runtimes before they commit to a fragile agent stack.

| Lens | Definition |
|---|---|
| Buyer or user | AI platform teams, developer-tool teams, and engineering leaders evaluating agent frameworks. |
| Commercial route | Offer runtime selection audits, benchmark customization, and CI evaluation packs for internal agent platforms. |
| Review signal | Standardized fixtures, comparative reports, deterministic runs, and reviewable benchmark outputs. |
| Safety boundary | Benchmarks are decision support, not universal model rankings; teams should extend fixtures to their real workflows. |
| Fast proof | Run the benchmark command, review generated reports, and compare framework behavior against the fixture suite. |

## Reviewer Fast Path

- **First minute:** Compare `results/latest.md` or the sample run before reading runner internals.
- **Local demo:** Run `make install-dev && make bench`; no model API key is required for the mock run.
- **Verification:** Run `make test` and `make lint`; rerender reports with `make report`.
- **Commercial read:** Sell it as an agent-framework selection audit and CI benchmark pack for AI platform teams.

## Commercialization Playbook

- [Monetization and GTM playbook](docs/monetization-playbook.md) maps the repository to buyer segments, offer ladder, pricing hypotheses, proof gates, and risk boundaries.

## Executive Proof Pack

- [Reviewer evidence map](docs/reviewer-evidence-map.md) gives a 7-minute route through the strongest hiring, buyer, and architecture signals.
- [Quality gate](docs/quality-gate.md) lists the local checks, CI surface, release boundary, and no-key/demo expectations for this repository.

## Why this exists

Teams picking between LangGraph, CrewAI, AutoGen, and home-grown
orchestrators currently have no apples-to-apples comparison. Public
benchmarks either optimise for narrow correctness metrics on toy prompts,
or they measure one framework in isolation with no shared task across
competitors. That gap leaves engineers relying on vendor marketing and
three-paragraph blog posts when picking a production orchestrator.

This repository provides a reproducible benchmark: one dataset, one set of
tools, one grading rubric, four runners. Every runner exposes the same
`BaseRunner` interface, so adding a fifth framework is a fifty-line pull
request. CI runs against a built-in deterministic mock LLM so the
numerical comparison of orchestrator *shape* requires no API key.

The four dimensions the benchmark cares about are the four that decide
whether an agent ships: correctness (does it pick the right tool?),
quality (is the answer acceptable?), cost (tokens, cash, wall-clock), and
reproducibility (does the same input produce the same calls?). Most
agent benchmarks leave the last dimension out; operators pay for that
every on-call rotation.

---

## Quick start

```bash
git clone https://github.com/KIM3310/agent-orchestration-benchmark.git
cd agent-orchestration-benchmark
make install-dev
make bench          # mock-LLM run, no API key required
```

Results land under `results/`:

```
results/
  latest.json        # machine-readable
  latest.md          # human-readable markdown
  latest.html        # standalone HTML report
```

To re-render reports without re-executing the benchmark:

```bash
python -m scripts.run_bench --report-only --input results/latest.json
```

For a live benchmark against real LLM APIs:

```bash
export OPENAI_API_KEY=sk-...
make bench-live
```

A working sample run is checked in at
[`results/sample_run_2026-04-16.json`](results/sample_run_2026-04-16.json).
The numbers in [Sample Results](#sample-results) are rendered from that
file.

---

## Architecture

```mermaid
flowchart LR
    F["fixtures/benchmark_prompts.jsonl<br/>(20 prompts)"] --> R
    subgraph Runner
      R["BenchmarkRunner"] --> A1["stage-pilot-style"]
      R --> A2["LangGraph"]
      R --> A3["CrewAI"]
      R --> A4["AutoGen"]
    end
    A1 & A2 & A3 & A4 --> TOOL["Shared tools<br/>query_sales_data · summarize_trend"]
    TOOL --> M["MetricsCollector<br/>latency · tokens · retries · fingerprints"]
    M --> RPT["Report generators<br/>JSON · Markdown · HTML"]
    RPT --> OUT[("results/*")]
```

The runner is pluggable: each framework adapter implements
`src.runners.base.BaseRunner` and is registered in
`scripts/run_bench.py`. Metrics and reports are framework-agnostic, so a
new adapter automatically inherits the full output pipeline.

---

## Frameworks benchmarked

| Framework | Version | Paradigm | Notes |
|---|---|---|---|
| [LangGraph](https://langchain-ai.github.io/langgraph/) | `0.2.55` | Stateful graph | Nodes + conditional edges. |
| [CrewAI](https://docs.crewai.com/) | `0.86.0` | Role-based crew | Agents with role/goal/backstory. |
| [AutoGen](https://microsoft.github.io/autogen/) | `0.4.0` | Conversational | Assistant + user proxy dialogue loop. |
| **stage-pilot-style** (this repo) | — | Deterministic tool-calling parser | ~200 LOC baseline modelled on [stage-pilot](https://github.com/KIM3310/stage-pilot). |

The fourth runner (`stage-pilot-style`) is a minimal in-house baseline.
It exists so the report answers the operator's real question: "is the
framework giving me net value over a well-designed script?"

All adapters default to a built-in mock LLM so CI runs are free and
deterministic; live mode is available for real-API comparisons.

---

## Metrics

| Metric | What it measures | Why operators care |
|---|---|---|
| `tool_call_success_rate` | Fraction of prompts whose observed tool sequence exactly matches the expected one. | If the agent calls the wrong tool or skips a tool, nothing else matters. |
| `final_answer_quality` | Fraction of final answers passing keyword + regex grading. | Proxy for user-visible correctness. |
| `latency_p50_ms / p95_ms / p99_ms` | Nearest-rank percentiles over per-prompt wall time. | Tail latency is what breaks SLOs. |
| `tokens_in / tokens_out` | Sum across all tool-calling rounds. | Upstream cost signal; independent of pricing. |
| `total_cost_usd` | Derived from the pricing table in `src/config.py`. | A concrete dollar number for budget pitches. |
| `retry_count` | Adapter-initiated retries across all prompts. | Fragility of the tool-call parser. |
| `exception_rate` | Fraction of prompts that raised. | Operators feel this as pages. |
| `deterministic_replay_rate` | Fraction of prompts whose replay fingerprints collapse to a single value. | Whether the orchestrator is reproducible under fixed input. |

See [`docs/methodology.md`](docs/methodology.md) for exact formulas, and
[ADR 002](docs/adr/002-metric-definitions.md) for the rationale.

---

## Sample results

Rendered from [`results/sample_run_2026-04-16.json`](results/sample_run_2026-04-16.json).
Lower is better for latency, cost, retries, and exception rate; higher is
better for everything else.

### Framework summary

| Framework | Tool Success | Answer Quality | p50 (ms) | p95 (ms) | p99 (ms) | Tokens In | Tokens Out | Cost (USD) | Retries | Exception Rate | Replay Stability |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stage-pilot-style | 1.000 | 0.950 | 8.4  | 21.3  | 32.1  | 1,709 | 1,217 | 0.000987 | 0 | 0.000 | 1.000 |
| langgraph         | 0.950 | 0.900 | 18.7 | 64.5  | 102.3 | 2,814 | 1,905 | 0.001565 | 3 | 0.050 | 0.900 |
| autogen           | 0.900 | 0.800 | 25.6 | 85.4  | 142.9 | 3,592 | 2,411 | 0.001985 | 5 | 0.050 | 0.850 |
| crewai            | 0.850 | 0.850 | 31.4 | 110.2 | 178.6 | 4,440 | 2,808 | 0.002352 | 7 | 0.100 | 0.750 |

### How to read this

* **stage-pilot-style** wins on both correctness and replay stability
  because it has no implicit state — every tool call is argument-checked
  and fingerprintable. It also wins on cost because the conversation
  pattern is shortest.
* **LangGraph** trails on cost and retry count mostly because its default
  tool-calling loop rehydrates extra state into the prompt. Tool success
  is close to parity.
* **CrewAI** is the slowest; the role-based hand-off between analyst and
  reporter roughly doubles the number of LLM calls per prompt. That also
  shows up as the highest retry count.
* **AutoGen** sits between LangGraph and CrewAI. Its proxy pattern is more
  predictable than CrewAI's role negotiation but less economical than a
  single-assistant loop.

Numbers are mock-LLM to keep the comparison reproducible. A live run with
`gpt-4o-mini` tends to widen CrewAI's and AutoGen's cost disadvantage,
because their patterns emit more completion tokens; the orderings are
stable.

### Per-framework deltas at a glance

| Framework | vs stage-pilot-style cost | vs stage-pilot-style p95 | Tool success delta |
|---|---:|---:|---:|
| langgraph | `+58.6 %` | `+203 %` | `-5 pp` |
| autogen   | `+101.1 %` | `+301 %` | `-10 pp` |
| crewai    | `+138.3 %` | `+417 %` | `-15 pp` |

---

## Extending

Adding a new framework is a four-step process:

1. Create `src/runners/<name>_runner.py` that subclasses
   `src.runners.base.BaseRunner`. Implement `run_prompt(prompt) -> PromptObservation`.
2. In mock mode, call `self.llm.complete(...)` exactly as the existing
   runners do; the benchmark guarantees determinism as long as you do.
3. Register the runner in `scripts/run_bench.py` (`FRAMEWORK_CHOICES`).
4. Add a test file under `tests/` that validates the runner on at least
   one fixture prompt.

A minimal adapter is roughly 40 lines. See
[`src/runners/autogen_runner.py`](src/runners/autogen_runner.py) for the
shortest existing example.

---

## Methodology

The benchmark isolates orchestrator behaviour by holding prompts, tools,
grading, and LLM backend constant. All LLM calls run against a seeded
mock in CI; live mode targets `gpt-4o-mini` by default. Every run records
per-prompt observations alongside the framework summary so the aggregate
can always be audited at the individual-call level. Full write-up:
[`docs/methodology.md`](docs/methodology.md).

Key invariants the benchmark enforces:

1. **Shared task.** Every framework receives the same twenty prompts and
   must produce an answer that satisfies the same keyword + regex grader.
2. **Shared tools.** The `query_sales_data` and `summarize_trend`
   implementations in `src/task.py` are pure functions of their input;
   identical arguments always produce identical output.
3. **Shared LLM.** The `MockLLM` in `src/runners/base.py` is seeded with
   `config.seed`. Frameworks do not get to bring their own completion
   strategy in CI.
4. **Bounded loops.** Every adapter caps its own loop count so a runaway
   orchestrator cannot distort aggregate metrics.
5. **Single source of truth for pricing.** `PRICING_USD_PER_MTOK` in
   `src/config.py` is the only place that translates tokens to dollars.

Related reading:

* [ADR 001: Framework Selection](docs/adr/001-framework-selection.md)
* [ADR 002: Metric Definitions](docs/adr/002-metric-definitions.md)
* [ADR 003: Determinism Requirements](docs/adr/003-determinism-requirements.md)
* [Results Interpretation Guide](docs/results-interpretation.md)

---

## Project structure

```
agent-orchestration-benchmark/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── .gitignore
├── .dockerignore
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   ├── __init__.py
│   ├── config.py              # models, pricing, retry budgets, timeouts
│   ├── task.py                # standardized task + deterministic tools
│   ├── fixtures.py            # prompt loader + grading contract
│   ├── metrics.py             # metric primitives + aggregation
│   ├── runner.py              # BenchmarkRunner (drives adapters)
│   ├── report.py              # JSON / Markdown / HTML renderers
│   └── runners/
│       ├── __init__.py
│       ├── base.py            # BaseRunner protocol + MockLLM
│       ├── langgraph_runner.py
│       ├── crewai_runner.py
│       ├── autogen_runner.py
│       └── stage_pilot_style.py  # deterministic tool-calling loop, ~200 LOC
├── tests/
│   ├── __init__.py
│   ├── test_task.py
│   ├── test_metrics.py
│   ├── test_stage_pilot_style.py
│   └── test_report.py
├── fixtures/
│   └── benchmark_prompts.jsonl   # 20 standardized prompts
├── results/
│   └── sample_run_2026-04-16.json
├── docs/
│   ├── methodology.md
│   ├── results-interpretation.md
│   └── adr/
│       ├── 001-framework-selection.md
│       ├── 002-metric-definitions.md
│       └── 003-determinism-requirements.md
└── scripts/
    ├── __init__.py
    ├── run_bench.py              # python -m scripts.run_bench
    └── run_bench.sh              # convenience wrapper
```

---

## Commands reference

| Command | What it does |
|---|---|
| `make install` | Install runtime dependencies. |
| `make install-dev` | Install runtime + dev dependencies (ruff, black, pytest, mypy). |
| `make test` | Run the pytest suite against the mock LLM. |
| `make lint` | Ruff over `src/` and `tests/`. |
| `make format` | Black + ruff `--fix`. |
| `make bench` | Full mock-LLM benchmark. |
| `make bench-live` | Full benchmark against real LLM APIs (requires `OPENAI_API_KEY`). |
| `make report` | Re-render the latest results as Markdown + HTML. |
| `make docker-build` | Build the Docker image. |
| `make docker-bench` | Run the benchmark inside Docker with a mounted results volume. |
| `make clean` | Remove build artefacts and caches. |

---

## Related projects

This benchmark complements several other tools published under
[@KIM3310](https://github.com/KIM3310):

* **[stage-pilot](https://github.com/KIM3310/stage-pilot)** — tool-calling
  reliability runtime (published as `@ai-sdk-tool/parser` on npm). The
  `stage_pilot_style` runner here is the Python-port distillation of its
  deterministic parser loop.
* **[Nexus-Hive](https://github.com/KIM3310/Nexus-Hive)** — multi-agent
  NL-to-SQL copilot. The analytics flavour of the benchmark task mirrors
  what Nexus-Hive agents do in production.
* **[AegisOps](https://github.com/KIM3310/AegisOps)** — multimodal incident
  analysis with operator handoff. Shares the "human-auditable tool trace"
  design principle used here.
* **[enterprise-llm-adoption-kit](https://github.com/KIM3310/enterprise-llm-adoption-kit)**
  — RAG + RBAC + audit reference stack. The benchmark's
  reproducible-fingerprint model is the orchestrator analogue of the
  audit log in that kit.
* **[districtpilot-ai](https://github.com/KIM3310/districtpilot-ai)** —
  Snowflake Korea Hackathon 2026 submission. A real-world deployment of
  a similar tool-calling agent shape.

---

## Citation

If you use this benchmark in a paper or blog post, please cite it as:

```bibtex
@software{kim2026agentbench,
  author  = {Doeon Kim},
  title   = {agent-orchestration-benchmark: A Reproducible Benchmark for
             LLM Agent Orchestration Frameworks},
  year    = {2026},
  url     = {https://github.com/KIM3310/agent-orchestration-benchmark},
  version = {0.1.0}
}
```

---

## Versioning and stability

The benchmark uses semantic-versioning-compatible tags. Breaking changes
to the metric schema or the prompt fixture set bump the minor version;
changes that affect only adapter internals bump the patch version. Every
release tag ships with a sample results file under `results/` so past
numbers stay reproducible after the tag.

Schema stability commitments:

* `summaries[*].framework` and every metric field in that object are
  stable. New metrics are added only in minor releases and default to
  `null` for older runs.
* `observations[framework][*]` objects keep `prompt_id`, `tool_calls`,
  `tokens_in`, `tokens_out`, `latency_ms`, `retry_count`, `exception`,
  and `replay_fingerprints`. Additional fields may appear.
* The report generators guarantee valid JSON, GitHub-flavored Markdown,
  and standalone HTML on any release.

If you consume this benchmark as input to a larger analysis pipeline,
pin the `agent-orchestration-benchmark` version in your lockfile and
store the generated JSON alongside your own artefacts.

## Contributing

Issues and pull requests are welcome. When proposing a new framework
adapter, please include:

1. The adapter file under `src/runners/`.
2. A test file under `tests/` covering at least one fixture prompt.
3. An ADR under `docs/adr/` explaining why the framework was added and
   what paradigm it represents.
4. An update to `scripts/run_bench.py::FRAMEWORK_CHOICES`.

The CI workflow in `.github/workflows/ci.yml` runs ruff, black, pytest,
and a dry-run mock benchmark on Python 3.11 and 3.12. New code should
clear all four lanes.

## Acknowledgements

This benchmark builds on the tool-calling reliability research behind
[stage-pilot](https://github.com/KIM3310/stage-pilot) and the
orchestration patterns used in [Nexus-Hive](https://github.com/KIM3310/Nexus-Hive).
Pricing figures are derived from each model provider's published
rates as of April 2026 and tracked in `src/config.py`.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Doeon Kim.

## Cloud + AI Architecture

This repository includes a neutral cloud and AI engineering blueprint that maps the current proof surface to runtime boundaries, data contracts, model-risk controls, deployment posture, and validation hooks.

- [Cloud + AI architecture blueprint](docs/cloud-ai-architecture.md)
- [Machine-readable architecture manifest](docs/architecture/blueprint.json)
- Validation command: `python3 scripts/validate_architecture_blueprint.py`

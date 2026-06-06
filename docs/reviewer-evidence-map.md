# Review Guide - agent-orchestration-benchmark

Updated: 2026-05-30

Use this page as the short path through the repository. It keeps the review grounded in the code, docs, commands, and boundaries that are already present.

## Summary

| Field | Notes |
|---|---|
| Lane | B2B AI platform evaluation |
| Core idea | Apples-to-apples benchmark for correctness, cost, latency, and deterministic replay. |
| Primary reader | AI platform leaders choosing LangGraph, CrewAI, AutoGen, or internal orchestration. |
| Stack | Python, Docker |

## Open First

1. Start with the README fast path and architecture section.
2. Open `docs/service-launch-playbook.md` only when reviewing the product or service angle.
3. Check the commands below before making claims about quality.
4. Skim the CI workflows and fixture data before deeper implementation review.
5. Read the boundaries section before presenting the project externally.

## Checks

| Purpose | Command |
|---|---|
| Test suite | `make test` |

## CI

- .github/workflows/architecture-blueprint.yml
- .github/workflows/ci.yml
- .github/workflows/dependency-review.yml
- .github/workflows/repository-health.yml
- .github/workflows/repository-surface.yml
- .github/workflows/secret-scan.yml

## Evidence

- pytest/ruff-style local verification path
- containerized delivery path
- Mock benchmark runs without keys
- Reports render reproducibly
- CI passes

## Commercial Notes

| Possible offer | Working scope assumption |
|---|---|
| Framework selection audit | $3k-$8k audit |
| Custom benchmark pack | $10k-$30k benchmark customization |
| CI eval integration | $2k-$7k/month eval maintenance |

## Boundaries

- Benchmarks are decision support
- Customer workflows need custom fixtures
- Avoid universal ranking claims

## Useful Metrics

- Fixture coverage
- Replay stability
- Decision cycle reduction

# ADR 001: Framework Selection

* **Status:** Accepted
* **Date:** 2026-04-16
* **Author:** Doeon Kim

## Context

Teams adopting LLM agents frequently compare four options: LangGraph,
CrewAI, AutoGen, and a hand-rolled orchestrator. Each markets a different
conceptual primitive (graph, role, conversation, deterministic parser).
Public comparisons exist, but most are single-run blog posts with no
reproducibility artefacts.

This benchmark must pick a small, tractable set of frameworks without
sacrificing relevance. More than four introduces maintenance burden;
fewer than three makes the comparison narrow.

## Decision

Include exactly four runners:

1. **LangGraph** — representative of graph-based orchestration.
2. **CrewAI** — representative of role-based orchestration.
3. **AutoGen** — representative of conversational orchestration.
4. **stage-pilot-style** — a deterministic tool-calling loop written in
   ~200 LOC, included as a control that measures what a minimal production
   orchestrator looks like.

Each runner implements a common `BaseRunner` protocol. CI runs against a
mock LLM so the comparison does not require API keys.

## Alternatives considered

* **Include LlamaIndex Agents.** Rejected for this initial release because
  its primary use case (retrieval) overlaps more with vector stores than
  with orchestrators. A future ADR may revisit.
* **Include Semantic Kernel.** Deferred: the abstraction set is closer to
  AutoGen than LangGraph, so including both would over-weight
  conversational orchestration.
* **Skip the stage-pilot-style control.** Rejected: without a minimal
  baseline the benchmark cannot answer the question "is the framework
  giving me net value over a script?"

## Consequences

* Adding a new framework requires a new adapter in `src/runners/` and a
  one-line registration in `scripts/run_bench.py`.
* Updates to any framework's SDK require a bump in the matching
  `pyproject.toml` extra. Live-mode code paths are tested in weekly CI
  rather than every commit to keep fast CI lanes fast.

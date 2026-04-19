"""Top-level benchmark runner.

The runner is pluggable: it accepts any object that implements the
:class:`src.runners.base.BaseRunner` protocol and drives it over the prompt
fixture. Per-prompt observations are collected into a
:class:`src.metrics.FrameworkSummary`, then passed to
:func:`src.report.write_all_reports` for rendering.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import RESULTS_DIR, BenchmarkConfig
from .fixtures import Prompt, load_prompts
from .metrics import FrameworkSummary, PromptObservation, aggregate
from .runners.base import BaseRunner
from .task import serialize_tool_calls

log = logging.getLogger(__name__)


class BenchmarkRunner:
    """Drive a set of framework runners over the benchmark fixture."""

    def __init__(
        self,
        runners: List[BaseRunner],
        prompts: Optional[List[Prompt]] = None,
        config: Optional[BenchmarkConfig] = None,
    ) -> None:
        self.runners = runners
        self.prompts = prompts if prompts is not None else load_prompts()
        self.config = config or BenchmarkConfig()
        self._prompts_by_id: Dict[str, Prompt] = {p.prompt_id: p for p in self.prompts}

    def run(self) -> Dict[str, object]:
        """Run every framework over every prompt and return a result dict.

        The dict is JSON-serializable and mirrors the shape of the file the
        report generators expect, so callers can both inspect results in
        memory and dump them to disk without conversion.
        """
        summaries: List[FrameworkSummary] = []
        per_framework_observations: Dict[str, List[PromptObservation]] = {}

        for runner in self.runners:
            log.info("running framework: %s", runner.name)
            observations = self._run_framework(runner)
            per_framework_observations[runner.name] = observations
            summary = aggregate(observations, self._prompts_by_id, self.config.model)
            summaries.append(summary)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": self.config.model,
            "n_prompts": len(self.prompts),
            "config": {
                "seed": self.config.seed,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
                "replay_trials": self.config.replay_trials,
                "use_mock_llm": self.config.use_mock_llm,
            },
            "summaries": [s.as_row() for s in summaries],
            "observations": {
                fw: [_obs_to_dict(o) for o in obs] for fw, obs in per_framework_observations.items()
            },
        }

    def _run_framework(self, runner: BaseRunner) -> List[PromptObservation]:
        observations: List[PromptObservation] = []
        for prompt in self.prompts:
            obs = self._run_prompt(runner, prompt)
            observations.append(obs)
        return observations

    def _run_prompt(self, runner: BaseRunner, prompt: Prompt) -> PromptObservation:
        """Execute a single prompt and capture replay fingerprints.

        The main trial's metrics are kept verbatim; replay trials only
        contribute to the ``replay_fingerprints`` list used by the
        deterministic-replay metric. Each trial starts with a fresh per-prompt
        state (``runner.reset_for_prompt``) so the mock LLM's state machine
        always starts from zero.
        """
        start = time.perf_counter()
        runner.reset_for_prompt(prompt)
        try:
            obs = runner.run_prompt(prompt)
        except Exception as exc:  # noqa: BLE001 - framework-level catchall
            log.exception("runner %s threw on %s", runner.name, prompt.prompt_id)
            return PromptObservation(
                prompt_id=prompt.prompt_id,
                framework=runner.name,
                final_answer="",
                exception=repr(exc),
                latency_ms=(time.perf_counter() - start) * 1000.0,
            )

        # Replay trials for determinism metric. We reuse the main trial's
        # fingerprint as the first entry so the list always has length
        # ``replay_trials``.
        fps = [_fingerprint(obs.tool_calls)]
        for _ in range(max(0, self.config.replay_trials - 1)):
            runner.reset_for_prompt(prompt)
            try:
                replay_obs = runner.run_prompt(prompt)
                fps.append(_fingerprint(replay_obs.tool_calls))
            except Exception:  # noqa: BLE001
                fps.append("exception")
        obs.replay_fingerprints = fps
        return obs


def _fingerprint(tool_calls) -> str:
    """Join the per-call fingerprints into a single string for comparison."""
    return "|".join(c.fingerprint() for c in tool_calls)


def _obs_to_dict(obs: PromptObservation) -> Dict[str, object]:
    return {
        "prompt_id": obs.prompt_id,
        "framework": obs.framework,
        "final_answer": obs.final_answer,
        "tool_calls": serialize_tool_calls(obs.tool_calls),
        "tokens_in": obs.tokens_in,
        "tokens_out": obs.tokens_out,
        "latency_ms": round(obs.latency_ms, 3),
        "retry_count": obs.retry_count,
        "exception": obs.exception,
        "replay_fingerprints": obs.replay_fingerprints,
    }


def write_results(result: Dict[str, object], destination: Optional[Path] = None) -> Path:
    """Persist a results dict to ``results/`` and return the path written."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if destination is None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        destination = RESULTS_DIR / f"run_{stamp}.json"
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return destination

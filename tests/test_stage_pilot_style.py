"""End-to-end tests for the stage-pilot-style runner using the mock LLM."""

from __future__ import annotations

from src.config import BenchmarkConfig
from src.fixtures import Prompt, load_prompts
from src.runners.base import MockLLM
from src.runners.stage_pilot_style import StagePilotStyleRunner


def _runner() -> StagePilotStyleRunner:
    cfg = BenchmarkConfig(use_mock_llm=True)
    return StagePilotStyleRunner(config=cfg, llm=MockLLM(seed=cfg.seed))


def test_runner_produces_expected_tool_sequence():
    prompt = Prompt(
        prompt_id="p-test-1",
        user_message="Find the top 3 revenue departments in Q1 2024 vs Q4 2023.",
        expected_tool_sequence=("query_sales_data", "summarize_trend"),
        answer_keywords=("revenue",),
        answer_regex="",
        difficulty="easy",
    )
    obs = _runner().run_prompt(prompt)
    observed = [c.name for c in obs.tool_calls if c.ok]
    assert observed == ["query_sales_data", "summarize_trend"]
    assert obs.final_answer != ""
    assert obs.tokens_in > 0
    assert obs.tokens_out > 0


def test_runner_final_answer_contains_revenue_phrase():
    prompt = Prompt(
        prompt_id="p-test-2",
        user_message="Show the top 3 highest-revenue departments in Q1 2024 versus Q4 2023.",
        expected_tool_sequence=("query_sales_data", "summarize_trend"),
        answer_keywords=("revenue",),
        answer_regex="",
        difficulty="easy",
    )
    obs = _runner().run_prompt(prompt)
    assert "Revenue" in obs.final_answer or "revenue" in obs.final_answer


def test_runner_emits_stable_fingerprint_across_runs():
    prompt = Prompt(
        prompt_id="p-test-3",
        user_message="Summarize Q1 2024 vs Q4 2023 revenue for the top 3 departments.",
        expected_tool_sequence=("query_sales_data", "summarize_trend"),
        answer_keywords=("revenue",),
        answer_regex="",
        difficulty="easy",
    )
    a = _runner().run_prompt(prompt)
    b = _runner().run_prompt(prompt)
    fingerprints_a = [c.fingerprint() for c in a.tool_calls if c.ok]
    fingerprints_b = [c.fingerprint() for c in b.tool_calls if c.ok]
    assert fingerprints_a == fingerprints_b


def test_runner_respects_fixture_file():
    prompts = load_prompts()
    assert len(prompts) == 20
    first = prompts[0]
    obs = _runner().run_prompt(first)
    assert obs.prompt_id == first.prompt_id

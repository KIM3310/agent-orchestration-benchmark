"""Tests for metric primitives and aggregation."""

from __future__ import annotations

import pytest

from src.fixtures import Prompt
from src.metrics import (
    PromptObservation,
    aggregate,
    answer_quality,
    percentile,
    tool_call_success,
)
from src.task import ToolCallRecord


def _prompt() -> Prompt:
    return Prompt(
        prompt_id="p-x",
        user_message="x",
        expected_tool_sequence=("query_sales_data", "summarize_trend"),
        answer_keywords=("alpha",),
        answer_regex="",
        difficulty="easy",
    )


def test_tool_call_success_matches_exact_sequence():
    obs = PromptObservation(
        prompt_id="p-x",
        framework="t",
        final_answer="",
        tool_calls=[
            ToolCallRecord("query_sales_data", {}, True, ""),
            ToolCallRecord("summarize_trend", {}, True, ""),
        ],
    )
    assert tool_call_success(obs, _prompt()) is True


def test_tool_call_success_fails_on_extra_call():
    obs = PromptObservation(
        prompt_id="p-x",
        framework="t",
        final_answer="",
        tool_calls=[
            ToolCallRecord("query_sales_data", {}, True, ""),
            ToolCallRecord("summarize_trend", {}, True, ""),
            ToolCallRecord("summarize_trend", {}, True, ""),
        ],
    )
    assert tool_call_success(obs, _prompt()) is False


def test_tool_call_success_ignores_failed_calls_when_counting():
    obs = PromptObservation(
        prompt_id="p-x",
        framework="t",
        final_answer="",
        tool_calls=[
            ToolCallRecord("query_sales_data", {}, False, "", error="bad"),
            ToolCallRecord("query_sales_data", {}, True, ""),
            ToolCallRecord("summarize_trend", {}, True, ""),
        ],
    )
    assert tool_call_success(obs, _prompt()) is True


def test_answer_quality_checks_keywords():
    obs = PromptObservation(prompt_id="p-x", framework="t", final_answer="Alpha matters")
    assert answer_quality(obs, _prompt()) is True
    obs.final_answer = "no such keyword"
    assert answer_quality(obs, _prompt()) is False


def test_percentile_handles_small_samples():
    assert percentile([10.0], 99) == 10.0
    assert percentile([], 50) == 0.0
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 50) == 3.0
    assert percentile(values, 99) == 5.0


def test_aggregate_computes_summary():
    prompts = {"p-x": _prompt()}
    obs_list = [
        PromptObservation(
            prompt_id="p-x",
            framework="demo",
            final_answer="Alpha result",
            tool_calls=[
                ToolCallRecord("query_sales_data", {}, True, ""),
                ToolCallRecord("summarize_trend", {}, True, ""),
            ],
            tokens_in=100,
            tokens_out=40,
            latency_ms=12.0,
            replay_fingerprints=["abc", "abc", "abc"],
        )
    ]
    summary = aggregate(obs_list, prompts, "gpt-4o-mini")
    row = summary.as_row()
    assert row["framework"] == "demo"
    assert row["tool_call_success_rate"] == 1.0
    assert row["final_answer_quality"] == 1.0
    assert row["deterministic_replay_rate"] == 1.0
    assert row["tokens_in"] == 100
    assert row["total_cost_usd"] > 0


def test_aggregate_rejects_empty_observations():
    with pytest.raises(ValueError):
        aggregate([], {}, "gpt-4o-mini")

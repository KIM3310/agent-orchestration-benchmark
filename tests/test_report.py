"""Tests for report rendering."""

from __future__ import annotations

import json

from src.report import framework_leaderboard, render_html, render_markdown


def _sample_result():
    return {
        "generated_at": "2026-04-16T00:00:00+00:00",
        "model": "gpt-4o-mini",
        "n_prompts": 20,
        "config": {"seed": 1, "replay_trials": 3, "temperature": 0.0, "max_tokens": 512, "use_mock_llm": True},
        "summaries": [
            {
                "framework": "stage-pilot-style",
                "n_prompts": 20,
                "tool_call_success_rate": 0.95,
                "final_answer_quality": 0.90,
                "latency_p50_ms": 10.0,
                "latency_p95_ms": 40.0,
                "latency_p99_ms": 60.0,
                "tokens_in": 1000,
                "tokens_out": 500,
                "total_cost_usd": 0.001,
                "retry_count": 1,
                "exception_rate": 0.0,
                "deterministic_replay_rate": 1.0,
            },
            {
                "framework": "langgraph",
                "n_prompts": 20,
                "tool_call_success_rate": 0.90,
                "final_answer_quality": 0.85,
                "latency_p50_ms": 20.0,
                "latency_p95_ms": 80.0,
                "latency_p99_ms": 110.0,
                "tokens_in": 1100,
                "tokens_out": 600,
                "total_cost_usd": 0.002,
                "retry_count": 3,
                "exception_rate": 0.05,
                "deterministic_replay_rate": 0.95,
            },
        ],
        "observations": {
            "stage-pilot-style": [
                {
                    "prompt_id": "p-001",
                    "framework": "stage-pilot-style",
                    "final_answer": "Revenue increased...",
                    "tool_calls": [
                        {"name": "query_sales_data", "arguments": {}, "ok": True, "result_preview": "", "error": None},
                        {"name": "summarize_trend", "arguments": {}, "ok": True, "result_preview": "", "error": None},
                    ],
                    "tokens_in": 50,
                    "tokens_out": 25,
                    "latency_ms": 10.0,
                    "retry_count": 0,
                    "exception": "",
                    "replay_fingerprints": ["a", "a", "a"],
                }
            ]
        },
    }


def test_markdown_contains_header_and_rows():
    md = render_markdown(_sample_result())
    assert "# Agent Orchestration Benchmark Results" in md
    assert "stage-pilot-style" in md
    assert "langgraph" in md
    assert "| Framework |" in md


def test_html_contains_table_structure():
    html = render_html(_sample_result())
    assert "<html" in html
    assert "<table" in html
    assert "stage-pilot-style" in html


def test_json_roundtrip_is_stable():
    result = _sample_result()
    blob = json.dumps(result)
    back = json.loads(blob)
    assert back["n_prompts"] == result["n_prompts"]


def test_leaderboard_ranks_by_combined_score():
    order = list(framework_leaderboard(_sample_result()))
    assert order[0] == "stage-pilot-style"
    assert set(order) == {"stage-pilot-style", "langgraph"}
